# VieScanner Backend

FastAPI backend for CCCD OCR extraction and Excel export.

## Features

- `POST /api/extract`: OCR image -> structured CCCD fields + confidences
- `POST /api/export`: CCCD JSON -> `.xlsx` file
- Switchable OCR mode: `mock` or `real`
- Centralized error handling with request correlation id
- OCR debug artifacts and tuning scripts

## Requirements

- Python 3.13
- Windows PowerShell (commands below use Windows paths)

Optional for faster inference:

- NVIDIA GPU (CUDA) for Torch/Paddle

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
JWT_SECRET=CHANGE_ME
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
```

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
- `OCR_DETECTOR_MODEL`
- `OCR_DETECTOR_CONF_THRESHOLD`
- `OCR_DETECTOR_PADDING`
- `OCR_RECOGNIZER_MODEL`
- `OCR_RECOGNIZER_BEAMSEARCH`
- `OCR_EXTRACTOR_FUZZY_THRESHOLD`
- `OCR_DEBUG_SAVE`

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
