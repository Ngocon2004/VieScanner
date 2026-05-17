# VieScanner Architecture

## Scope

VieScanner focuses on one core use case:

- Input: front-side Vietnamese CCCD image
- Output: validated structured data + Excel export

## High-Level Components

```text
[Browser / Next.js]
    |
    | 1) POST /api/extract (multipart image)
    v
[FastAPI Controller]
    |
    | 2) OCR Engine (mock or real)
    v
[OCR Pipeline: align -> clean -> detect -> recognize -> extract]
    |
    | 3) JSON {data, confidences}
    v
[Browser Form]
    |
    | 4) POST /api/export (CCCDData)
    v
[Excel Service]
    |
    | 5) .xlsx stream + Content-Disposition
    v
[Browser Download]
```

## Backend Layering

```text
controllers/   HTTP boundary only (request/response)
models/        Pydantic schemas and validation rules
services/      Business logic (OCR orchestration, Excel generation)
repositories/  Data access abstractions (model weight paths)
core/          Cross-cutting concerns (config, logging, middleware, errors)
utils/         Shared helper functions
```

### Why this split

- Controllers stay thin and testable.
- OCR logic remains independent from FastAPI details.
- Pipeline stages are swappable through interfaces (`mock` <-> `real`).
- Weight/model path access is centralized.

## Request Lifecycle

1. `RequestContextMiddleware` assigns `X-Request-ID`.
2. Controller validates inputs (image or JSON body).
3. Service runs OCR or Excel generation.
4. Domain exceptions map to consistent error JSON.
5. Response includes the same `X-Request-ID` for log correlation.

## Error Handling Contract

All known errors are returned in this format:

```json
{
  "code": "ocr_failed",
  "message": "Khong the trich xuat thong tin tu anh.",
  "request_id": "<uuid>",
  "details": []
}
```

Main families:

- `image_invalid` (400)
- `ocr_failed` + stage-specific mapped codes (422)
- `validation_error` (422)
- `excel_failed` / `internal_error` (500)

## OCR Execution Modes

- `OCR_ENGINE=mock`: deterministic scaffolding for dev/tests.
- `OCR_ENGINE=real`: full ML pipeline.
- `OCR_ENGINE=hybrid`: reserved mode (currently fallback to mock).

## Observability

- Structured log format with request id.
- Per-stage timing in OCR pipeline trace (`decode/align/clean/detect/recognize/extract`).
- Optional debug artifacts (`OCR_DEBUG_SAVE=true`) saved under `backend/debug_images/`.

## Security and Data Handling Notes

- Real CCCD images and ground-truth files are excluded by gitignore.
- Debug/tuning artifacts can contain PII; keep local only.
- Current project scope intentionally skips auth/compliance hardening (student demo scope).
