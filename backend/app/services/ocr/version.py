"""Phiên bản pipeline OCR, gắn vào nhãn engine của scan để làm khóa cache kết quả.

Cache trước đây chỉ khóa theo (ảnh, user, "real"): sửa pipeline xong, ảnh đã quét vẫn nhận kết quả cũ.
Phiên bản = hash mã nguồn `app/services/ocr/` (kể cả danh mục JSON) + builder engine + các cấu hình
OCR_* ảnh hưởng kết quả, nên tự đổi mỗi khi logic/cấu hình đổi mà không cần ai nhớ tăng số.
"""

from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path

from app.core.config import settings

_OCR_DIR = Path(__file__).parent
_ENGINE_BUILDER = _OCR_DIR.parent / "ocr_engine.py"
# Cấu hình không đổi nội dung kết quả (thiết bị, cache, debug, concurrency...).
_IGNORED_SETTINGS = frozenset({
    "ocr_engine", "ocr_device", "ocr_model_dir", "ocr_debug_save", "ocr_max_concurrency",
    "ocr_warmup_on_startup", "ocr_result_cache_enabled", "ocr_result_cache_ttl_seconds",
})


@lru_cache(maxsize=1)
def _source_digest() -> str:
    digest = hashlib.sha1()
    files = [p for p in _OCR_DIR.rglob("*") if p.suffix in {".py", ".json"} and "__pycache__" not in p.parts]
    for path in sorted([*files, _ENGINE_BUILDER]):
        digest.update(path.relative_to(_OCR_DIR.parent).as_posix().encode())
        # Chuẩn hóa xuống dòng để cùng mã nguồn cho cùng phiên bản trên Windows/Linux.
        digest.update(path.read_bytes().replace(b"\r\n", b"\n"))
    return digest.hexdigest()


def pipeline_version() -> str:
    config = {
        key: value
        for key, value in settings.model_dump().items()
        if key.startswith("ocr_") and key not in _IGNORED_SETTINGS
    }
    payload = _source_digest() + json.dumps(config, sort_keys=True, default=str)
    return hashlib.sha1(payload.encode()).hexdigest()[:8]


def engine_label(*, cached: bool = False) -> str:
    """Nhãn lưu ở `scans.ocr_engine` (tối đa 32 ký tự), vd `real@1a2b3c4d` / `real@1a2b3c4d:cache`."""
    label = f"{settings.ocr_engine}@{pipeline_version()}"
    return f"{label}:cache" if cached else label


__all__ = ["engine_label", "pipeline_version"]
