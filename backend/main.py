import asyncio
from contextlib import asynccontextmanager, suppress

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.body_limit import RequestBodyLimitMiddleware

from app.controllers import (
    admin_controller,
    auth_controller,
    export_controller,
    jobs_controller,
    ocr_controller,
    records_controller,
    scans_controller,
)
from app.core.config import settings
from app.core.error_handlers import register_exception_handlers
from app.core.logging import configure_logging, logger
from app.core.middleware import RequestContextMiddleware
from app.db.session import dispose_engine, ping_database
from app.services.jobs.worker import JobWorker
from app.services.ocr_engine import is_ocr_engine_ready, warmup_ocr_engine
from app.services.retention import retention_loop

configure_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(
        "VieScanner API starting | version={} | debug={}",
        settings.app_version,
        settings.debug,
    )
    if settings.jwt_secret_generated:
        logger.warning(
            "JWT_SECRET chưa được đặt: dùng khóa ngẫu nhiên, mọi phiên đăng nhập mất khi restart."
        )
    await ping_database()
    logger.info("Database ping OK")
    # M2: warm-up models trước khi nhận request để request đầu không bị chậm vì
    # phải tải YOLO/Paddle/VietOCR. Best-effort, không chặn startup nếu lỗi.
    if settings.ocr_warmup_on_startup:
        await warmup_ocr_engine()
    # M5: job dọn scan cũ chạy nền (tắt khi SCAN_RETENTION_DAYS=0).
    retention_task: asyncio.Task[None] | None = None
    if settings.scan_retention_days > 0:
        retention_task = asyncio.create_task(retention_loop())
        logger.info(
            "Scan retention enabled | days={} | every {}h",
            settings.scan_retention_days,
            settings.scan_retention_interval_hours,
        )
    app.state.job_worker = JobWorker()
    await app.state.job_worker.start()
    yield
    await app.state.job_worker.stop()
    if retention_task is not None:
        retention_task.cancel()
        with suppress(asyncio.CancelledError):
            await retention_task
    await dispose_engine()
    logger.info("VieScanner API shutting down")


app = FastAPI(
    title=settings.app_name,
    description="API for extracting information from Vietnamese CCCD cards",
    version=settings.app_version,
    lifespan=lifespan,
)

# FastAPI tự dựng middleware stack nên bỏ qua tham số `max_body_size` của Starlette: phải thêm tay.
# Request khai báo Content-Length đã bị RequestContextMiddleware chặn trước; middleware này đếm byte
# thật cho body gửi kiểu chunked.
app.add_middleware(RequestBodyLimitMiddleware, max_body_size=settings.max_request_bytes)
app.add_middleware(RequestContextMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID", "Content-Disposition"],
)

register_exception_handlers(app)

app.include_router(ocr_controller.router, prefix="/api", tags=["OCR"])
app.include_router(export_controller.router, prefix="/api", tags=["Export"])
app.include_router(auth_controller.router, prefix="/api", tags=["Auth"])
app.include_router(scans_controller.router, prefix="/api", tags=["Scans"])
app.include_router(records_controller.router, prefix="/api", tags=["Records"])
app.include_router(jobs_controller.router, prefix="/api", tags=["Jobs"])
app.include_router(admin_controller.router, prefix="/api", tags=["Admin"])


@app.get("/")
async def root():
    return {"message": "Welcome to VieScanner API"}


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "version": settings.app_version,
        "ocr_engine": settings.ocr_engine.lower(),
        "ocr_engine_ready": is_ocr_engine_ready(),
        "job_queue_size": worker.qsize() if (worker := getattr(app.state, "job_worker", None)) else None,
    }


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=settings.debug)
