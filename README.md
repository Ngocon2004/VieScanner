# VieScanner

VieScanner is a student project that extracts structured data from Vietnamese CCCD images and exports the result to Excel.

## What It Does

- Upload CCCD front-side images (JPG/PNG/WebP/HEIC) or PDF files (one card per page).
- Scan with the device camera: framing guide, live quality hints, auto-capture.
- Pre-check image quality and show per-image rejection/warning reasons.
- Process in the background (job queue) with live progress and cancel.
- Run OCR pipeline (mock or full real pipeline).
- Return structured fields with per-field confidence.
- Let users edit low-confidence fields before export.
- Export final data to `.xlsx`.

## Demo Flow

1. Upload images/PDF or capture with the camera in the Next.js UI (images are resized in a Web Worker).
2. Frontend pre-checks obvious low-quality images, then calls `POST /api/jobs` and gets a `job_id` immediately.
3. Frontend polls `GET /api/jobs/{id}`; each item ends with `{ status, quality, data, confidences }`.
4. Every extracted card is added to one editable list (name, CCCD number, date of birth, gender, permanent residence); front and back of the same card merge by CCCD number. Low-confidence cells are highlighted, and rows that are missing data or contradict their CCCD number block the export.
5. Frontend calls `POST /api/export-list` and downloads one Excel file with one row per person.

## Tech Stack

- Frontend: Next.js 16, React 19, TypeScript, Tailwind CSS, Zod, Sonner
- Backend: FastAPI, Pydantic v2, Loguru, Pandas/OpenPyXL
- OCR: YOLO (aligner), OpenCV (cleaner), PaddleOCR (detector), VietOCR (recognizer), rule-based extractor
- Testing: Pytest (backend), Vitest + Testing Library (frontend)

## Quick Start

### Prerequisites

- Node.js 20+
- Python 3.13

### 1) Run Backend

```bash
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload
```

By default, backend runs `OCR_ENGINE=mock` (no heavy ML runtime needed).

### 2) Run Frontend

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000`.

## Real OCR Mode

To enable full OCR pipeline (`OCR_ENGINE=real`), follow model/dependency instructions in:

- [backend/README.md](./backend/README.md)
- [docs/OCR_PIPELINE.md](./docs/OCR_PIPELINE.md)

## Tests

Backend:

```bash
cd backend
venv\Scripts\python -m pytest -q
```

Frontend:

```bash
cd frontend
npm test
```

## Project Structure

```text
VieScanner/
|- backend/                 # FastAPI API + OCR pipeline
|- frontend/                # Next.js web app
|- docs/                    # Architecture and OCR docs
|- PROJECT_ROADMAP.md       # Sprint roadmap and current status
|- Logic_Project.md         # System flow and project phase diagrams
`- README.md
```

## Documentation

- [Backend Setup](./backend/README.md)
- [Frontend Setup](./frontend/README.md)
- [Architecture](./docs/ARCHITECTURE.md)
- [OCR Pipeline Details](./docs/OCR_PIPELINE.md)
- [Troubleshooting (No-Hang Checklist)](./README_TROUBLESHOOTING.md)
- [Roadmap](./PROJECT_ROADMAP.md)
- [Master Plan (front + back CCCD)](./docs/MASTER_PLAN.md)
- [Logic Project (diagrams)](./Logic_Project.md)

## Current Status

Core OCR pipeline, UX polish, and selective tests are done. Documentation is in progress (screenshots/demo video/slides still pending).

## License

For academic/demo use. Add a formal license file if this project is distributed publicly.
