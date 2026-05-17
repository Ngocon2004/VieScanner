"""Repository quản lý truy cập tới các file weights ML.

Đóng vai trò "data access layer" cho ML weights – tách biệt logic resolve path
ra khỏi service code. Khi chuyển sang lưu weights ở S3 / cloud storage, chỉ cần
sửa repository này, các service không bị ảnh hưởng.
"""

from __future__ import annotations

from pathlib import Path

from app.core.config import settings
from app.core.logging import logger


class ModelWeightsRepository:
    """Resolve & validate đường dẫn các file weights trong thư mục `weights/`.

    Args:
      base_dir: thư mục root chứa weights. Mặc định lấy từ `settings.ocr_model_dir`.
    """

    # Map tên logic → tên file thực tế. Khi đổi version model chỉ cần đổi value.
    _WEIGHT_FILES: dict[str, str] = {
        "card_aligner": "model_crop.pt",
        # "text_detector": "PP-OCRv5_server_det.onnx",  # Phase 2.3
        # "text_recognizer": "vgg_transformer.pth",     # Phase 2.4
    }

    def __init__(self, base_dir: str | Path | None = None) -> None:
        self.base_dir = Path(base_dir) if base_dir is not None else Path(settings.ocr_model_dir)

    def get_path(self, weight_name: str) -> Path:
        """Trả về Path tuyệt đối tới file weight. KHÔNG check tồn tại."""
        if weight_name not in self._WEIGHT_FILES:
            raise KeyError(
                f"Weight '{weight_name}' chưa được đăng ký trong "
                f"ModelWeightsRepository (đã có: {list(self._WEIGHT_FILES)})."
            )
        return self.base_dir / self._WEIGHT_FILES[weight_name]

    def require_path(self, weight_name: str) -> Path:
        """Như `get_path` nhưng raise FileNotFoundError nếu thiếu file."""
        path = self.get_path(weight_name)
        if not path.exists():
            raise FileNotFoundError(
                f"Không tìm thấy weight '{weight_name}' tại '{path}'. "
                f"Hãy download file vào thư mục '{self.base_dir}/'."
            )
        logger.debug("ModelWeightsRepository: resolved {} → {}", weight_name, path)
        return path

    def exists(self, weight_name: str) -> bool:
        """Tiện cho health check."""
        try:
            return self.get_path(weight_name).exists()
        except KeyError:
            return False


__all__ = ["ModelWeightsRepository"]
