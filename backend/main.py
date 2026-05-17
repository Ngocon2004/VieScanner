from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.controllers import (
    auth_controller,
    export_controller,
    ocr_controller,
    records_controller,
    scans_controller,
)
from app.core.config import settings
from app.core.error_handlers import register_exception_handlers
from app.core.logging import configure_logging, logger
from app.core.middleware import RequestContextMiddleware
from app.db.session import dispose_engine, ping_database

configure_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(
        "VieScanner API starting | version={} | debug={}",
        settings.app_version,
        settings.debug,
    )
    await ping_database()
    logger.info("Database ping OK")
    yield
    await dispose_engine()
    logger.info("VieScanner API shutting down")


app = FastAPI(
    title=settings.app_name,
    description="API for extracting information from Vietnamese CCCD cards",
    version=settings.app_version,
    lifespan=lifespan,
)

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


@app.get("/")
async def root():
    return {"message": "Welcome to VieScanner API"}


@app.get("/health")
async def health():
    return {"status": "ok", "version": settings.app_version}


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=settings.debug)
