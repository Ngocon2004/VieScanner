"""Central application settings for VieScanner backend."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ----- App -----
    app_name: str = "VieScanner API"
    app_version: str = "1.0.0"
    debug: bool = False

    # ----- CORS -----
    cors_origins_raw: str = "http://localhost:3000"

    # ----- Upload limits -----
    max_upload_size_mb: int = 5
    allowed_mime_types_raw: str = "image/jpeg,image/png,image/webp"

    # ----- OCR engine -----
    ocr_engine: str = "mock"
    ocr_device: str = "auto"
    ocr_model_dir: str = "weights"

    ocr_aligner_conf_threshold: float = 0.25
    ocr_aligner_retry_conf_thresholds_raw: str = "0.15,0.10,0.05"

    ocr_detector_model: str = "PP-OCRv5_server_det"
    ocr_detector_conf_threshold: float = 0.25
    ocr_detector_padding: int = 4

    ocr_cleaner_shadow_kernel_size: int = 7
    ocr_cleaner_clip_hist_percent: float = 1.0

    ocr_recognizer_model: str = "vgg_transformer"
    ocr_recognizer_beamsearch: bool = True

    ocr_extractor_fuzzy_threshold: int = 80
    ocr_debug_save: bool = False
    ocr_max_image_side_px: int = 2000
    ocr_result_cache_enabled: bool = True
    ocr_result_cache_ttl_seconds: int = 86400

    # ----- Image quality gate (pre-OCR) -----
    # Cổng kiểm tra chất lượng ảnh trước OCR. Ngưỡng "hard" => chặn (không OCR);
    # ngưỡng "soft" => vẫn OCR nhưng cảnh báo. Tắt bằng `QUALITY_CHECK_ENABLED=false`.
    quality_check_enabled: bool = True
    quality_max_batch_files: int = 20
    # Độ phân giải: cạnh ngắn (px). Nhỏ hơn hard -> chặn; nhỏ hơn soft -> cảnh báo.
    quality_min_side_hard_px: int = 320
    quality_min_side_soft_px: int = 640
    # Độ nét: variance của Laplacian. Thấp hơn hard -> mờ nặng (chặn); thấp hơn soft -> cảnh báo.
    quality_blur_var_hard: float = 30.0
    quality_blur_var_soft: float = 100.0
    # Độ sáng: mean luma (0-255). Quá tối / quá sáng.
    quality_dark_hard: float = 35.0
    quality_dark_soft: float = 65.0
    quality_bright_hard: float = 243.0
    quality_bright_soft: float = 220.0
    # Lóa/cháy sáng: tỉ lệ pixel gần trắng (0-1). Cao hơn hard -> chặn; cao hơn soft -> cảnh báo.
    quality_glare_hard: float = 0.30
    quality_glare_soft: float = 0.12
    # Kiểm tra "có phải thẻ CCCD" bằng YOLO (chỉ hiệu lực khi OCR_ENGINE=real).
    quality_card_check_enabled: bool = True

    # ----- Database -----
    # Production: postgresql+asyncpg://user:pass@host:5432/dbname
    database_url: str = "sqlite+aiosqlite:///./viescanner.db"
    database_echo: bool = False

    # ----- Auth / JWT -----
    auth_required: bool = False
    jwt_secret: str = "CHANGE_ME"
    jwt_algorithm: str = "HS256"
    jwt_access_expire_min: int = 60
    jwt_refresh_expire_days: int = 7

    @property
    def cors_origins(self) -> list[str]:
        return _split_csv(self.cors_origins_raw)

    @property
    def allowed_mime_types(self) -> list[str]:
        return _split_csv(self.allowed_mime_types_raw)

    @property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024

    @property
    def ocr_aligner_retry_conf_thresholds(self) -> list[float]:
        values: list[float] = []
        for item in _split_csv(self.ocr_aligner_retry_conf_thresholds_raw):
            try:
                v = round(float(item), 4)
            except ValueError:
                continue
            values.append(max(0.0, min(1.0, v)))
        return values


settings = Settings()
