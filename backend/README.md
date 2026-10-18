﻿# VieScanner Backend

FastAPI backend for CCCD OCR extraction and Excel export.

## Features

- `POST /api/extract`: OCR one image -> structured CCCD fields + confidences
- `POST /api/extract-batch`: quality-check and OCR multiple CCCD images
- `POST /api/export`: CCCD JSON -> `.xlsx` file
- `POST /api/export-list`: reviewed list of people -> one `.xlsx` (STT, name, CCCD number, date of birth, gender, permanent residence); rejects rows whose gender/birth year contradict the CCCD number
- `GET /api/admin/*`: admin dashboard data (overview, system, users, recent scans; admin only). Grant admin with `scripts/create_admin.py`; see `docs/ADMIN_DASHBOARD.md`
- Switchable OCR mode: `mock` or `real`
- Pre-OCR image quality gate with per-image rejection reasons
- Centralized error handling with request correlation id
- OCR debug artifacts and tuning scripts

## Requirements

- Python 3.13
- Windows PowerShell (commands below use Windows paths)

Optional for faster inference:

- NVIDIA GPU (CUDA) for Torch/Paddle. Text detection drops from ~9s to ~0.15s per image
  with the GPU build of Paddle (see the `paddlepaddle-gpu` note in `requirements.txt`;
  it reuses Torch's CUDA/cuDNN DLLs, so install Torch cu128 first).

## Setup

### 1) Create virtual environment

```bash
cd backend
python -m venv venv
venv\Scripts\activate
python -m pip install --upgrade pip
```

### 2) Install core dependencies

```bash
pip install -r requirements.txt
```

Optional, only for data-preparation scripts run once on a developer machine (not needed by the server or Docker):

```bash
pip install -r requirements-tools.txt   # pyosmium: reads OpenStreetMap .osm.pbf files
```

### 3) Install VietOCR (manual, required for `OCR_ENGINE=real`)

`vietocr==0.3.13` should be installed with `--no-deps` to avoid Pillow conflict on Python 3.13.

```bash
pip install einops gdown prefetch_generator imgaug albumentations lmdb scikit-image "pillow>=10.4"
pip install vietocr==0.3.13 --no-deps
```

### 4) Configure environment

```bash
copy .env.example .env
```

Default `.env.example` runs `OCR_ENGINE=mock`.

### 5) Database setup (new DB layer)

Default local DB is SQLite async:

```env
DATABASE_URL=sqlite+aiosqlite:///./viescanner.db
DATABASE_ECHO=false
AUTH_REQUIRED=false
JWT_SECRET=CHANGE_ME   # để mặc định thì server tự sinh khóa tạm (đăng nhập mất khi restart); production phải đặt chuỗi ngẫu nhiên dài
JWT_ALGORITHM=HS256
JWT_ACCESS_EXPIRE_MIN=60
JWT_REFRESH_EXPIRE_DAYS=7
```

Run initial migration:

```bash
venv\Scripts\alembic -c app/db/alembic.ini upgrade head
```

Rollback one revision (verification/debug):

```bash
venv\Scripts\alembic -c app/db/alembic.ini downgrade -1
venv\Scripts\alembic -c app/db/alembic.ini upgrade head
```

### 6) Download YOLO aligner weight (real OCR only)

```bash
curl -L https://raw.githubusercontent.com/denghwee/OCR_Vietnamese_Read_CCCD/master/model/model_crop.pt -o weights/model_crop.pt
```

## Run Server

```bash
uvicorn main:app --reload
```

- API root: `http://localhost:8000`
- Swagger: `http://localhost:8000/docs`

Health check:

```bash
curl http://localhost:8000/health
# { "status": "ok", "version": "1.0.0", "ocr_engine": "mock", "ocr_engine_ready": true }
```

`ocr_engine_ready` becomes `true` once models are warmed up at startup (see
`OCR_WARMUP_ON_STARTUP`). For `OCR_ENGINE=real` this means YOLO/PaddleOCR/VietOCR
are loaded, so the first real request is no longer slow.

## API Contract

### `POST /api/extract`

Request: multipart form with field `file`.

Success response:

```json
{
  "data": { "id_number": "001202000123" },
  "scan_id": "uuid-or-null",
  "confidences": { "id_number": 0.99 },
  "quality": {
    "accepted": true,
    "score": 1.0,
    "issues": [],
    "metrics": { "min_side_px": 760 }
  }
}
```

If the image fails a hard quality check, the endpoint returns `422` with
`code: "image_quality_low"` and `details` containing the quality issues.

### `POST /api/jobs` (recommended for many files)

Request: multipart form with repeated field `files` (max `QUALITY_MAX_BATCH_FILES`)
and optional `source` (`upload` | `camera`). Accepts JPG/PNG/WebP, HEIC (converted
to JPEG) and PDF (each page rendered at `IMPORT_PDF_DPI` becomes one item).

Response `202`: the job with its items in `queued` state. Processing runs in a
background worker (same quality gate → cache → OCR as `/extract-batch`).

- `GET /api/jobs/{id}`: progress (`processed_items/total_items`) and per-item
  `result` (same shape as a `/extract-batch` result). Item `status`: `queued`,
  `processing`, `done`, `rejected`, `failed`, `cancelled`. Job `status`: `queued`,
  `processing`, `completed`, `partial`, `failed`, `cancelled`.
- `POST /api/jobs/{id}/cancel`, `DELETE /api/jobs/{id}`, `GET /api/jobs` (logged-in user).
- Anonymous jobs are reachable by their UUID; jobs of a logged-in user only by that user.
- Uploaded bytes live only in `JOB_TMP_DIR` until processed (max `JOB_TTL_MINUTES`);
  jobs are deleted after `JOB_RETENTION_DAYS`. On restart, pending items are resumed.
- Limits: `IMPORT_MAX_FILE_MB`, `IMPORT_PDF_MAX_PAGES`, `JOB_MAX_ITEMS`.

### `POST /api/extract-batch` (synchronous, kept for compatibility)

Request: multipart form with repeated field `files` (max
`QUALITY_MAX_BATCH_FILES`, default `20`).

Response:

```json
{
  "total": 2,
  "accepted_count": 1,
  "rejected_count": 1,
  "results": [
    {
      "index": 0,
      "filename": "ok.png",
      "accepted": true,
      "status": "extracted",
      "quality": { "accepted": true, "score": 1.0, "issues": [], "metrics": {} },
      "data": { "id_number": "001202000123" },
      "confidences": { "id_number": 0.99 },
      "scan_id": "uuid-or-null",
      "error_code": null,
      "error_message": null
    }
  ]
}
```

`status` values:

- `extracted`: image passed quality checks and OCR succeeded.
- `rejected`: image failed validation or a hard quality check.
- `ocr_failed`: image passed quality checks but OCR failed.

## OCR Modes

Set in `.env`:

- `OCR_ENGINE=mock`: fast dev mode, no heavy OCR runtime.
- `OCR_ENGINE=real`: full OCR pipeline:
  - Aligner: YOLO
  - Cleaner: OpenCV
  - Detector: PaddleOCR
  - Recognizer: VietOCR
  - Extractor: rule-based

Useful tuning vars:

- `OCR_ALIGNER_CONF_THRESHOLD`
- `OCR_ALIGNER_RETRY_CONF_THRESHOLDS_RAW`
- `OCR_ALIGNER_CONTOUR_FALLBACK`
- `OCR_DETECTOR_MODEL`
- `OCR_DETECTOR_CONF_THRESHOLD`
- `OCR_DETECTOR_PADDING`
- `OCR_RECOGNIZER_MODEL`
- `OCR_RECOGNIZER_BEAMSEARCH`
- `OCR_RECOGNIZER_BATCH` — recognize all boxes in one `predict_batch` call
  (faster, real per-line confidence; uses greedy decoding so it bypasses
  beamsearch). Set `false` to prefer beamsearch accuracy via per-box `predict`.
- `OCR_EXTRACTOR_FUZZY_THRESHOLD`
- `OCR_DEBUG_SAVE`

Image quality gate:

- `QUALITY_CHECK_ENABLED` (default `true`) enables pre-OCR checks.
- `QUALITY_MAX_BATCH_FILES` caps `/extract-batch` uploads.
- `QUALITY_MIN_SIDE_HARD_PX` / `QUALITY_MIN_SIDE_SOFT_PX` check resolution.
- `QUALITY_BLUR_VAR_HARD` / `QUALITY_BLUR_VAR_SOFT` check sharpness.
- `QUALITY_DARK_HARD` / `QUALITY_DARK_SOFT` check under-exposure.
- `QUALITY_BRIGHT_HARD` / `QUALITY_BRIGHT_SOFT` check over-exposure.
- `QUALITY_GLARE_HARD` / `QUALITY_GLARE_SOFT` check glare/washed-out pixels.
- `QUALITY_CARD_CHECK_ENABLED` enables YOLO card-presence check in
  `OCR_ENGINE=real`: `not_cccd` is hard, `card_partial` is soft. This uses the
  same aligner retry thresholds to reduce false rejects on difficult photos.

Stability / performance:

- `OCR_MAX_CONCURRENCY` (default `1`) — max OCR requests running in parallel.
  Models are shared singletons and not thread-safe, so `1` avoids crashes / GPU
  OOM. Raise on multi-core CPU or GPUs with spare VRAM.
- `OCR_WARMUP_ON_STARTUP` (default `true`) — load models during app startup
  (`lifespan`) so the first request is fast. Only meaningful for `OCR_ENGINE=real`.

Scan history (`scans` table):

- Successful `/extract` and `/extract-batch` results are persisted to `scans`
  via **FastAPI background tasks** (M4): the `scan_id` is pre-generated and
  returned immediately, while the DB write happens after the response is sent —
  so the commit no longer blocks the response. Failed requests are still logged
  synchronously.
- `SCAN_RETENTION_DAYS` (default `0` = keep everything) — when `> 0`, a startup +
  periodic job (`SCAN_RETENTION_INTERVAL_HOURS`, default `24`) deletes scans
  older than N days so the table does not grow unbounded (M5). Related
  `corrections` are removed and `cccd_records` are unlinked (`scan_id` → NULL).

## Tests

Run all backend tests:

```bash
venv\Scripts\python -m pytest -q
```

Coverage:

```bash
venv\Scripts\python -m pytest --cov=app --cov-report=term-missing -q
```

## OCR Evaluation Scripts

### Batch evaluation

```bash
venv\Scripts\python scripts\eval_ocr.py <image_folder> --out scripts/eval_results.json
```

With ground truth:

```bash
venv\Scripts\python scripts\eval_ocr.py <image_folder> --ground-truth <ground_truth.json> --out scripts/eval_results_gt.json
```

### Grid tuning

```bash
venv\Scripts\python scripts\tune_ocr_grid.py <image_folder> --ground-truth <ground_truth.json> --out scripts/tune_results.json
```

## Debug Artifacts

If `OCR_DEBUG_SAVE=true`, each OCR run stores:

- input image
- aligned image
- cleaned image
- detector boxes overlay
- output JSON with lines + result

Output folder: `backend/debug_images/<timestamp>_<id>/`

## Project Layout

```text
backend/
|- app/
|  |- controllers/          # HTTP routes
|  |- core/                 # config, logging, middleware, exceptions
|  |- models/               # Pydantic schemas
|  |- repositories/         # model weight path resolver
|  |- services/
|  |  |- excel_service.py
|  |  `- ocr/               # OCR interfaces, pipeline, stages
|  `- utils/
|- scripts/                 # evaluation and tuning scripts
|- tests/
|- weights/
`- main.py
```
