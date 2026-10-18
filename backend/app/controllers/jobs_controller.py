"""Job API: nhận nhiều ảnh/PDF, trả `job_id` ngay, xử lý nền và cho phép theo dõi tiến độ."""

from __future__ import annotations

import asyncio
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile, status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import ImageValidationError, VieScannerError
from app.core.logging import logger
from app.db.models.job import TERMINAL_JOB_STATUSES, Job, JobItemStatus, JobSource, JobStatus
from app.db.models.user import User
from app.db.repositories.job_repository import JobRepository
from app.db.session import get_db
from app.dependencies.auth import get_current_user, get_optional_user
from app.models.cccd import BatchItemResult, ErrorResponse
from app.models.job import JobRead, JobSummary
from app.services.intake import IntakeItem, IntakeLimitError, plan_upload, save_upload
from app.services.jobs import tmp_store
from app.services.jobs.worker import JobWorker
from app.utils.image import safe_upload_filename

router = APIRouter(prefix="/jobs")


class JobNotFoundError(VieScannerError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "job_not_found"
    message = "Không tìm thấy job."


class JobWorkerUnavailableError(VieScannerError):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    code = "job_worker_unavailable"
    message = "Bộ xử lý nền chưa sẵn sàng. Vui lòng thử lại sau."


def _worker(request: Request) -> JobWorker:
    worker = getattr(request.app.state, "job_worker", None)
    if worker is None:
        raise JobWorkerUnavailableError()
    return worker


async def _owned_job(repo: JobRepository, job_id: str, user: User | None) -> Job:
    job = await repo.get(job_id)
    # Job ẩn danh chỉ truy cập được bằng UUID khó đoán; job có chủ chỉ chủ xem được.
    if job is None or (job.user_id is not None and (user is None or user.id != job.user_id)):
        raise JobNotFoundError()
    return job


def _rejected_result(item: IntakeItem, seq: int) -> dict:
    return BatchItemResult(
        index=seq, filename=item.filename, accepted=False, status="rejected",
        error_code=item.error_code, error_message=item.error_message,
    ).model_dump(mode="json")


@router.post(
    "",
    response_model=JobRead,
    status_code=status.HTTP_202_ACCEPTED,
    responses={400: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
    summary="Tạo job xử lý nhiều ảnh CCCD (JPG/PNG/WebP/HEIC/PDF)",
)
async def create_job(
    request: Request,
    files: list[UploadFile] = File(...),
    source: str = Form("upload"),
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_optional_user),
) -> JobRead:
    worker = _worker(request)
    if source not in (JobSource.UPLOAD.value, JobSource.CAMERA.value):
        raise ImageValidationError("Nguồn không hợp lệ (upload hoặc camera).", code="invalid_source")
    if not files:
        raise ImageValidationError("Chưa chọn file nào để xử lý.")
    if len(files) > settings.quality_max_batch_files:
        raise ImageValidationError(
            f"Chỉ nhận tối đa {settings.quality_max_batch_files} file mỗi lần (bạn gửi {len(files)})."
        )

    # File gốc được ghi ra đĩa trước khi có bản ghi job nên id job sinh sẵn để đặt thư mục tạm.
    job_id = str(uuid4())
    intake: list[IntakeItem] = []
    repo = JobRepository(db)
    try:
        for upload_index, file in enumerate(files):
            filename = safe_upload_filename(file.filename)
            path = tmp_store.upload_path(job_id, upload_index)
            try:
                await asyncio.to_thread(save_upload, file.file, path)
            except ImageValidationError as exc:
                intake.append(
                    IntakeItem(upload_index, filename, error_code=exc.code, error_message=exc.message)
                )
                continue
            planned = await asyncio.to_thread(plan_upload, upload_index, filename, path)
            if all(item.error_code for item in planned):
                path.unlink(missing_ok=True)
            intake.extend(planned)
            if len(intake) > settings.job_max_items:
                raise IntakeLimitError(
                    f"Tổng số ảnh/trang vượt giới hạn {settings.job_max_items} mỗi job."
                )

        job_source = JobSource(source)
        if job_source == JobSource.UPLOAD and any(i.page_number is not None for i in intake):
            job_source = JobSource.IMPORT_PDF

        rows = [
            {
                "upload_index": item.upload_index,
                "filename": item.filename,
                "container_filename": item.container_filename,
                "page_number": item.page_number,
                "status": JobItemStatus.REJECTED if item.error_code else JobItemStatus.QUEUED,
                "result": _rejected_result(item, seq) if item.error_code else None,
            }
            for seq, item in enumerate(intake)
        ]
        job = await repo.create(
            job_id=job_id,
            user_id=user.id if user else None,
            source=job_source,
            ocr_engine=settings.ocr_engine,
            items=rows,
        )
        await repo.refresh_progress(job.id)
        await db.commit()
    except BaseException:
        tmp_store.delete_job(job_id)
        raise
    job = await repo.get(job.id)

    queued = [row for row in job.items if row.status == JobItemStatus.QUEUED]
    for row in queued:
        worker.enqueue(job.id, row.id)
    if not queued:
        tmp_store.delete_job(job.id)

    logger.info(
        "job created | id={} source={} items={} queued={}",
        job.id, job_source.value, len(rows), len(queued),
    )
    return JobRead.model_validate(job)


@router.get("", response_model=list[JobSummary], responses={401: {"model": ErrorResponse}})
async def list_jobs(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[JobSummary]:
    jobs = await JobRepository(db).list_by_user(user_id=user.id, limit=limit, offset=offset)
    return [JobSummary.model_validate(job) for job in jobs]


@router.get("/{job_id}", response_model=JobRead, responses={404: {"model": ErrorResponse}})
async def get_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_optional_user),
) -> JobRead:
    return JobRead.model_validate(await _owned_job(JobRepository(db), job_id, user))


@router.post("/{job_id}/cancel", response_model=JobRead, responses={404: {"model": ErrorResponse}})
async def cancel_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_optional_user),
) -> JobRead:
    repo = JobRepository(db)
    job = await _owned_job(repo, job_id, user)
    if job.status not in TERMINAL_JOB_STATUSES:
        job.status = JobStatus.CANCELLED
        await repo.cancel_queued_items(job_id)
        await repo.refresh_progress(job_id)
        await db.commit()
        job = await repo.get(job_id)
        for item in job.items:
            if item.status == JobItemStatus.CANCELLED:
                tmp_store.delete_item(job_id, item.id)
    return JobRead.model_validate(job)


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT, responses={404: {"model": ErrorResponse}})
async def delete_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_optional_user),
) -> Response:
    repo = JobRepository(db)
    await _owned_job(repo, job_id, user)
    await repo.delete(job_id)
    await db.commit()
    tmp_store.delete_job(job_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
