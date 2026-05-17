# VieScanner

VieScanner is a student project that extracts structured data from Vietnamese CCCD images and exports the result to Excel.

## What It Does

- Upload a CCCD front-side image from desktop or mobile camera.
- Run OCR pipeline (mock or full real pipeline).
- Return structured fields with per-field confidence.
- Let users edit low-confidence fields before export.
- Export final data to `.xlsx`.

## Demo Flow

1. Upload image in the Next.js UI.
2. Frontend calls `POST /api/extract`.
3. Backend OCR pipeline returns `{ data, confidences }`.
4. User reviews and edits fields.
5. Frontend calls `POST /api/export` and downloads Excel.

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
- [PHASE_2_PLAN.md](./PHASE_2_PLAN.md)

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
|- PHASE_2_PLAN.md          # Detailed OCR phase plan
`- README.md
```

## Documentation

- [Backend Setup](./backend/README.md)
- [Frontend Setup](./frontend/README.md)
- [Architecture](./docs/ARCHITECTURE.md)
- [OCR Pipeline Details](./docs/OCR_PIPELINE.md)
- [Roadmap](./PROJECT_ROADMAP.md)

## Current Status

Core OCR pipeline, UX polish, and selective tests are done. Documentation is in progress (screenshots/demo video/slides still pending).

## License

For academic/demo use. Add a formal license file if this project is distributed publicly.
