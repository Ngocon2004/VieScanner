"""Central application settings for VieScanner backend."""

from __future__ import annotations

import secrets

from pydantic_settings import BaseSettings, SettingsConfigDict

_INSECURE_JWT_SECRETS = {"", "CHANGE_ME", "changeme", "secret"}


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    def model_post_init(self, __context) -> None:  # noqa: ANN001
        # Khóa mặc định công khai trong repo = ai cũng ký được token admin. Thiếu khóa thật thì
        # dùng khóa ngẫu nhiên (token mất hiệu lực khi restart) thay vì chạy với khóa đoán được.
        if self.jwt_secret.strip() in _INSECURE_JWT_SECRETS:
            self.jwt_secret = secrets.token_urlsafe(48)
            self.jwt_secret_generated = True

    # ----- App -----
    app_name: str = "VieScanner API"
    app_version: str = "1.0.0"
    debug: bool = False

    # ----- CORS -----
    cors_origins_raw: str = "http://localhost:3000"

    # ----- Upload limits -----
    # Tổng dung lượng 1 request (mọi file + phần bao multipart). Không giới hạn thì body bị Starlette
    # ghi hết ra đĩa tạm trước khi endpoint kiểm tra từng file -> có thể làm đầy đĩa.
    max_request_mb: int = 100
    max_upload_size_mb: int = 5
    allowed_mime_types_raw: str = "image/jpeg,image/png,image/webp"

    # ----- OCR engine -----
    ocr_engine: str = "mock"
    ocr_device: str = "auto"
    ocr_model_dir: str = "weights"

    ocr_aligner_conf_threshold: float = 0.25
    ocr_aligner_retry_conf_thresholds_raw: str = "0.15,0.10,0.05"
    ocr_aligner_contour_fallback: bool = True

    ocr_detector_model: str = "PP-OCRv5_server_det"
    ocr_detector_conf_threshold: float = 0.25
    ocr_detector_padding: int = 4

    ocr_cleaner_shadow_kernel_size: int = 7
    ocr_cleaner_clip_hist_percent: float = 1.0

    ocr_recognizer_model: str = "vgg_transformer"
    ocr_recognizer_beamsearch: bool = True
    # Nhận dạng cả batch box trong 1 lần thay vì lặp từng box -> giảm latency stage chậm nhất.
    # vgg_transformer dùng bộ giải mã gộp 1 vòng (`_decode_transformer_batch`, chữ trùng
    # `predict_batch` của VietOCR, nhanh ~3x). LƯU Ý: batch luôn greedy (bỏ qua beamsearch)
    # nhưng trả confidence thật cho mỗi dòng. Tắt (=false) nếu muốn ưu tiên beamsearch.
    ocr_recognizer_batch: bool = True

    ocr_extractor_fuzzy_threshold: int = 80
    ocr_debug_save: bool = False
    ocr_max_image_side_px: int = 2000
    # Số request OCR được phép chạy song song. Engine là singleton, model
    # (YOLO/Paddle/VietOCR) dùng chung và KHÔNG thread-safe -> mặc định 1 để
    # tránh crash/OOM (đặc biệt GPU 4GB). Tăng nếu CPU nhiều core / GPU dư VRAM.
    ocr_max_concurrency: int = 1
    # Warm-up models lúc startup (lifespan) để request đầu không bị chậm vì phải
    # tải YOLO/Paddle/VietOCR. Chỉ tốn ý nghĩa khi OCR_ENGINE=real.
    ocr_warmup_on_startup: bool = True
    ocr_result_cache_enabled: bool = True
    ocr_result_cache_ttl_seconds: int = 86400
    # Đọc QR mặt trước CCCD gắn chip (2021+) -> độ chính xác gần tuyệt đối cho
    # các trường QR cung cấp (số CCCD, họ tên, ngày sinh, giới tính, nơi thường
    # trú). OCR vẫn chạy để bù trường QR không có + làm fallback khi không có QR.
    ocr_qr_enabled: bool = True
    # Kết quả kém (<=3 trường hoặc số CCCD không hợp lệ) -> phân loại hướng thẻ, xoay và OCR lại 1 lần.
    ocr_orientation_retry: bool = True
    ocr_orientation_model: str = "PP-LCNet_x1_0_doc_ori"

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

    # ----- Import (PDF/HEIC) -----
    import_max_file_mb: int = 50
    import_pdf_dpi: int = 200
    import_pdf_max_pages: int = 100
    # Ảnh chụp nhiều thẻ được tách thành từng ảnh một thẻ (app/services/card_split.py).
    import_split_multi_cards: bool = True

    # ----- Jobs (xử lý bất đồng bộ) -----
    job_max_items: int = 200
    job_tmp_dir: str = "tmp/jobs"
    # Ảnh gốc chỉ nằm trong thư mục tạm tối đa chừng này phút (không lưu ảnh CCCD lâu dài).
    job_ttl_minutes: int = 60
    job_retention_days: int = 7
    job_cleanup_interval_minutes: int = 10

    # ----- Database -----
    # Production: postgresql+asyncpg://user:pass@host:5432/dbname
    database_url: str = "sqlite+aiosqlite:///./viescanner.db"
    database_echo: bool = False

    # ----- Scan retention (M5) -----
    # Tự động xóa scan cũ hơn N ngày để bảng `scans` không phình (mỗi request,
    # kể cả cache hit, đều ghi 1 row). 0 = tắt (mặc định, giữ toàn bộ lịch sử);
    # đặt >0 (vd 30) để bật. Job chạy lúc startup + lặp lại theo chu kỳ dưới.
    scan_retention_days: int = 0
    scan_retention_interval_hours: int = 24

    # ----- Auth / JWT -----
    auth_required: bool = False
    jwt_secret: str = "CHANGE_ME"
    jwt_secret_generated: bool = False
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
    def max_request_bytes(self) -> int:
        return self.max_request_mb * 1024 * 1024

    @property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024

    @property
    def import_max_file_bytes(self) -> int:
        return self.import_max_file_mb * 1024 * 1024

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
