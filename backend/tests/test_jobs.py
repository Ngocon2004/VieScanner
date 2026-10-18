from __future__ import annotations

import asyncio
import io
import os
import time
from collections.abc import AsyncGenerator, Generator

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.db.base import Base
from app.db.session import get_db
from app.db.models.job import JobItemStatus, JobSource
from app.db.repositories.job_repository import JobRepository
from app.services import intake
from app.services.jobs import tmp_store
from app.services.jobs.worker import JobWorker
from main import app

TERMINAL = {"completed", "partial", "failed", "cancelled"}


def _jpeg(seed: int, size: tuple[int, int] = (900, 560)) -> bytes:
    np = pytest.importorskip("numpy")
    rng = np.random.default_rng(seed)
    pixels = rng.integers(60, 200, (size[1], size[0], 3), dtype=np.uint8)
    buf = io.BytesIO()
    Image.fromarray(pixels).save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def _pdf(pages: int) -> bytes:
    images = [Image.open(io.BytesIO(_jpeg(100 + i))) for i in range(pages)]
    buf = io.BytesIO()
    images[0].save(buf, format="PDF", save_all=True, append_images=images[1:], resolution=100)
    return buf.getvalue()


def _heic() -> bytes:
    pillow_heif = pytest.importorskip("pillow_heif")
    pillow_heif.register_heif_opener()
    buf = io.BytesIO()
    Image.open(io.BytesIO(_jpeg(7))).save(buf, format="HEIF")
    return buf.getvalue()


@pytest.fixture
def jobs_client(tmp_path, monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient, None, None]:
    # SQLite file (mỗi session một kết nối như production). DB in-memory + StaticPool dùng chung
    # 1 kết nối: request đóng session sẽ rollback luôn cập nhật dở của worker -> test chập chờn.
    monkeypatch.setattr(settings, "job_tmp_dir", str(tmp_path / "jobs"))
    monkeypatch.setattr(settings, "ocr_engine", "mock")
    engine = create_async_engine(f"sqlite+aiosqlite:///{(tmp_path / 'jobs.db').as_posix()}")
    factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)

    async def _create_schema() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db] = _override_get_db
    try:
        with TestClient(app) as client:
            client.portal.call(_create_schema)
            app.state.job_worker.session_factory = lambda: factory
            yield client
    finally:
        app.dependency_overrides.pop(get_db, None)
        asyncio.run(engine.dispose())


def _wait(client: TestClient, job_id: str, headers: dict | None = None) -> dict:
    deadline = time.time() + 15
    while time.time() < deadline:
        body = client.get(f"/api/jobs/{job_id}", headers=headers or {}).json()
        if body["status"] in TERMINAL:
            return body
        time.sleep(0.05)
    raise AssertionError(f"job {job_id} did not finish: {body}")


def test_job_processes_images_and_reports_bad_files(jobs_client: TestClient, tmp_path) -> None:
    files = [
        ("files", ("a.jpg", _jpeg(1), "image/jpeg")),
        ("files", ("b.jpg", _jpeg(2), "image/jpeg")),
        ("files", ("notes.txt", b"hello", "text/plain")),
    ]
    created = jobs_client.post("/api/jobs", files=files)
    assert created.status_code == 202
    body = created.json()
    assert body["total_items"] == 3
    assert body["items"][2]["status"] == "rejected"
    assert body["items"][2]["result"]["error_code"] == "unsupported_file"

    done = _wait(jobs_client, body["id"])
    assert done["status"] == "partial"
    assert done["succeeded_items"] == 2
    assert done["failed_items"] == 1
    extracted = [i for i in done["items"] if i["status"] == "done"]
    assert all(i["result"]["data"]["id_number"] for i in extracted)
    assert all(i["result"]["scan_id"] == i["scan_id"] for i in extracted)
    assert [i["upload_index"] for i in done["items"]] == [0, 1, 2]
    assert not (tmp_path / "jobs" / body["id"]).exists()


def test_job_expands_pdf_pages(jobs_client: TestClient) -> None:
    created = jobs_client.post(
        "/api/jobs", files=[("files", ("hoso.pdf", _pdf(2), "application/pdf"))]
    )
    assert created.status_code == 202
    body = created.json()
    assert body["source"] == JobSource.IMPORT_PDF.value
    assert [(i["container_filename"], i["page_number"]) for i in body["items"]] == [
        ("hoso.pdf", 1),
        ("hoso.pdf", 2),
    ]
    assert _wait(jobs_client, body["id"])["succeeded_items"] == 2


def test_job_converts_heic(jobs_client: TestClient) -> None:
    created = jobs_client.post(
        "/api/jobs", files=[("files", ("IMG_0001.HEIC", _heic(), "image/heic"))]
    )
    assert created.status_code == 202
    item = created.json()["items"][0]
    assert item["status"] == "queued"


def test_job_rejects_when_pages_exceed_limit(
    jobs_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "job_max_items", 2)
    response = jobs_client.post(
        "/api/jobs", files=[("files", ("big.pdf", _pdf(3), "application/pdf"))]
    )
    assert response.status_code == 400
    assert response.json()["code"] == "import_too_large"


def test_job_rejects_invalid_source(jobs_client: TestClient) -> None:
    response = jobs_client.post(
        "/api/jobs",
        files=[("files", ("a.jpg", _jpeg(3), "image/jpeg"))],
        data={"source": "import_zip"},
    )
    assert response.status_code == 400


def test_cancel_marks_queued_items_cancelled(
    jobs_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(app.state.job_worker, "enqueue", lambda *_: None)
    files = [("files", (f"{i}.jpg", _jpeg(10 + i), "image/jpeg")) for i in range(2)]
    job_id = jobs_client.post("/api/jobs", files=files).json()["id"]

    body = jobs_client.post(f"/api/jobs/{job_id}/cancel").json()
    assert body["status"] == "cancelled"
    assert {i["status"] for i in body["items"]} == {"cancelled"}
    assert jobs_client.delete(f"/api/jobs/{job_id}").status_code == 204
    assert jobs_client.get(f"/api/jobs/{job_id}").status_code == 404


def test_job_of_a_user_is_hidden_from_others(jobs_client: TestClient) -> None:
    jobs_client.post(
        "/api/auth/register",
        json={"email": "owner@example.com", "password": "secret123", "full_name": "Owner"},
    )
    token = jobs_client.post(
        "/api/auth/login", json={"email": "owner@example.com", "password": "secret123"}
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    job_id = jobs_client.post(
        "/api/jobs", files=[("files", ("a.jpg", _jpeg(20), "image/jpeg"))], headers=headers
    ).json()["id"]

    assert jobs_client.get(f"/api/jobs/{job_id}", headers=headers).status_code == 200
    assert jobs_client.get(f"/api/jobs/{job_id}").status_code == 404
    listed = jobs_client.get("/api/jobs", headers=headers).json()
    assert [j["id"] for j in listed] == [job_id]


@pytest.mark.asyncio
async def test_worker_recovers_pending_items_and_handles_missing_tmp(
    session_factory: async_sessionmaker[AsyncSession], tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "job_tmp_dir", str(tmp_path / "jobs"))
    async with session_factory() as session:
        repo = JobRepository(session)
        job = await repo.create(
            user_id=None,
            source=JobSource.UPLOAD,
            ocr_engine="mock",
            items=[
                {"upload_index": 0, "filename": "a.jpg", "status": JobItemStatus.PROCESSING},
                {"upload_index": 1, "filename": "b.jpg", "status": JobItemStatus.QUEUED},
            ],
        )
        await session.commit()
        job_id = job.id
        item_ids = [i.id for i in job.items]
    tmp_store.write_item(job_id, item_ids[0], _jpeg(30))

    worker = JobWorker(session_factory=lambda: session_factory)
    await worker.recover()
    assert worker.qsize() == 2

    await worker.process_item(job_id, item_ids[0])
    await worker.process_item(job_id, item_ids[1])

    async with session_factory() as session:
        job = await JobRepository(session).get(job_id)
        statuses = [i.status for i in job.items]
        assert statuses == [JobItemStatus.DONE, JobItemStatus.REJECTED]
        assert job.items[1].result["error_code"] == "file_expired"
        assert job.status.value == "partial"


def test_intake_sniffs_formats_and_reports_broken_pdf() -> None:
    assert intake.sniff_kind(_jpeg(40)) == "image"
    assert intake.sniff_kind(_pdf(1)) == "pdf"
    assert intake.sniff_kind(b"GIF89a....") is None

    broken = intake.expand_file(0, "bad.pdf", b"%PDF-1.7\nnot really a pdf")
    assert broken[0].error_code == "file_unreadable"


def test_intake_rejects_pdf_over_page_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "import_pdf_max_pages", 1)
    items = intake.expand_file(0, "two.pdf", _pdf(2))
    assert items[0].error_code == "pdf_too_many_pages"


@pytest.mark.asyncio
async def test_worker_marks_item_failed_when_engine_cannot_load(
    session_factory: async_sessionmaker[AsyncSession], tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "job_tmp_dir", str(tmp_path / "jobs"))
    async with session_factory() as session:
        job = await JobRepository(session).create(
            user_id=None,
            source=JobSource.UPLOAD,
            ocr_engine="real",
            items=[{"upload_index": 0, "filename": "a.jpg", "status": JobItemStatus.QUEUED}],
        )
        await session.commit()
        job_id, item_id = job.id, job.items[0].id
    tmp_store.write_item(job_id, item_id, _jpeg(50))

    def missing_weights():
        raise FileNotFoundError("model_crop.pt")

    worker = JobWorker(session_factory=lambda: session_factory, engine_provider=missing_weights)
    await worker.process_item(job_id, item_id)

    async with session_factory() as session:
        job = await JobRepository(session).get(job_id)
        assert job.items[0].status == JobItemStatus.FAILED
        assert job.items[0].result["error_code"] == "ocr_engine_crashed"
        assert "model_crop" not in job.items[0].result["error_message"]
        assert job.status.value == "failed"
    assert worker._seen == {}


def test_intake_caps_render_size_of_huge_pdf_pages(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "ocr_max_image_side_px", 800)
    big = Image.new("RGB", (6000, 4000), "white")
    buf = io.BytesIO()
    big.save(buf, format="PDF", resolution=20)
    items = intake.expand_file(0, "poster.pdf", buf.getvalue())
    assert items[0].error_code is None
    assert max(Image.open(io.BytesIO(items[0].contents)).size) <= 800


@pytest.mark.asyncio
async def test_cleanup_keeps_images_of_jobs_still_waiting_in_the_queue(
    session_factory: async_sessionmaker[AsyncSession], tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "job_tmp_dir", str(tmp_path / "jobs"))
    async with session_factory() as session:
        repo = JobRepository(session)
        waiting = await repo.create(
            user_id=None, source=JobSource.UPLOAD, ocr_engine="mock",
            items=[{"upload_index": 0, "filename": "a.jpg", "status": JobItemStatus.QUEUED}],
        )
        await session.commit()
        waiting_id, item_id = waiting.id, waiting.items[0].id
    tmp_store.write_item(waiting_id, item_id, b"x")
    tmp_store.write_item("finished-job", "i1", b"x")
    old = time.time() - 2 * 3600
    for name in (waiting_id, "finished-job"):
        os.utime(tmp_path / "jobs" / name, (old, old))

    await JobWorker(session_factory=lambda: session_factory).cleanup_once()

    assert tmp_store.read_item(waiting_id, item_id) == b"x"
    assert not (tmp_path / "jobs" / "finished-job").exists()
    very_old = time.time() - 25 * 3600
    os.utime(tmp_path / "jobs" / waiting_id, (very_old, very_old))
    assert tmp_store.purge_expired(3600, frozenset({waiting_id})) == [waiting_id]


def _two_card_photo() -> bytes:
    cv2 = pytest.importorskip("cv2")
    np = pytest.importorskip("numpy")
    img = np.full((1500, 2000, 3), 245, np.uint8)
    for x in (200, 1100):
        cv2.rectangle(img, (x, 300), (x + 540, 300 + 856), (190, 200, 120), -1)
        cv2.putText(img, "CAN CUOC", (x + 40, 500), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (20, 20, 20), 3)
    return cv2.imencode(".jpg", img)[1].tobytes()


def test_multi_card_photo_is_split_by_the_worker(jobs_client: TestClient) -> None:
    created = jobs_client.post("/api/jobs", files=[("files", ("hai_the.jpg", _two_card_photo(), "image/jpeg"))])
    body = created.json()
    # Tách thẻ chạy trong worker: request chỉ ghi file và trả về ngay 1 item cho ảnh gốc.
    assert [i["filename"] for i in body["items"]] == ["hai_the.jpg"]

    done = _wait(jobs_client, body["id"])
    assert done["total_items"] == 2
    assert [(i["filename"], i["container_filename"]) for i in done["items"]] == [
        ("hai_the.jpg - thẻ 1", "hai_the.jpg"),
        ("hai_the.jpg - thẻ 2", "hai_the.jpg"),
    ]


def test_cards_beyond_the_job_item_limit_are_reported_not_processed(
    jobs_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "job_max_items", 1)
    created = jobs_client.post("/api/jobs", files=[("files", ("hai_the.jpg", _two_card_photo(), "image/jpeg"))])
    done = _wait(jobs_client, created.json()["id"])
    codes = [(i["result"] or {}).get("error_code") for i in done["items"]]
    # Thẻ 1 vừa giới hạn nên vẫn được kiểm tra/OCR; thẻ 2 vượt giới hạn chỉ được báo lỗi.
    assert codes[0] != "import_too_large"
    assert codes[1] == "import_too_large"


def test_oversized_upload_is_rejected_while_streaming_to_disk(
    jobs_client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.setattr(settings, "max_upload_size_mb", 1)
    monkeypatch.setattr(settings, "import_max_file_mb", 1)
    big = b"%PDF-1.4\n" + b" " * (1024 * 1024)
    body = jobs_client.post("/api/jobs", files=[("files", ("big.pdf", big, "application/pdf"))]).json()
    assert body["items"][0]["status"] == "rejected"
    assert "1MB" in body["items"][0]["result"]["error_message"]
    assert not (tmp_path / "jobs" / body["id"]).exists()
