# AI Context - VieScanner

## Project Overview
VieScanner là ứng dụng web giúp tự động hóa việc đọc thông tin từ ảnh CCCD và xuất ra Excel.

## Tech Stack
- Frontend: Next.js + Tailwind CSS
- Backend: FastAPI (cấu trúc MVC + repositories)
- Data processing: Pandas
- AI/OCR: YOLO, PaddleOCR, VietOCR (Reference: denghwee/OCR_Vietnamese_Read_CCCD)

## Core Flow
1. User uploads CCCD image (Front side).
2. Backend crops and extracts text.
3. Backend returns JSON to Frontend.
4. User reviews and edits information in a form.
5. User clicks "Export", Backend generates .xlsx file and sends it back.

## Backend Architecture (MVC + Repositories)

```
backend/
├── main.py            # FastAPI entry: middleware, routers, lifespan
├── weights/           # ML weights (.pt) – gitignored except .gitkeep
└── app/
    ├── controllers/   # HTTP routers – tầng C (Controller)
    │   ├── ocr_controller.py        # POST /api/extract
    │   └── export_controller.py     # POST /api/export
    ├── models/        # Pydantic data shapes – tầng M (Model)
    │   └── cccd.py                  # CCCDData, ErrorResponse
    ├── services/      # Business logic
    │   ├── excel_service.py         # CCCDData → .xlsx
    │   ├── ocr_engine.py            # OCREngine wrapper + DI builder
    │   └── ocr/                     # OCR pipeline (5 stages)
    │       ├── interfaces.py        # Protocol cho từng stage
    │       ├── pipeline.py          # OCRPipeline orchestrator
    │       └── stages/              # MockX + RealX implementations
    ├── repositories/  # Data access layer
    │   └── model_weights_repository.py  # resolve weights/*.pt path
    ├── core/          # config, logging, middleware, exceptions
    └── utils/         # filename, image validation
```

## Standards
- Use TypeScript for Frontend.
- Use Pydantic models for Backend API (input + output).
- Controllers chỉ xử lý HTTP (request parse, validate, call service, format response).
- Services chứa business logic, không biết về FastAPI/HTTP.
- Repositories abstract data access (file weights, DB sau này).
- Keep OCR stages modular (Protocol + DI) cho dễ swap mock ↔ real.
## DB Layer Update (2026-05-17)
- Added async DB stack: SQLAlchemy 2.0 + Alembic + asyncpg/aiosqlite.
- Added modules: `app/db`, `app/models/orm`, `app/dependencies/auth`, `app/services/auth_service`.
- Added controllers: `auth_controller`, `scans_controller`, `records_controller`.
- `/api/extract` now logs scan history and returns optional `scan_id`.
- `/api/export` now persists `cccd_records`, marks `exported_at`, and logs corrections.
- Migration baseline: `backend/app/db/migrations/versions/0001_initial.py` for `users`, `scans`, `cccd_records`, `corrections`.
