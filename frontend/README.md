﻿# VieScanner Frontend

Next.js client for uploading CCCD images, reviewing OCR results, and exporting Excel.

## Features

- Drag-and-drop upload of JPG/PNG/WebP/HEIC and PDF (one card per page)
- Camera scan tab: framing guide, live hints (dark/glare/blur/motion), auto-capture
- Background job processing with progress bar and cancel (`POST /api/jobs` + polling)
- Image resize/compression in a Web Worker (main-thread fallback)
- Quality precheck for images before upload
- Skeleton loading during OCR
- Toast notifications for extract/export success and failures
- Realtime form validation with Zod
- Confidence badge per field (green/yellow/red)
- Auto-focus to the lowest-confidence field

## Requirements

- Node.js 20+
- npm 10+

## Setup

### 1) Install dependencies

```bash
cd frontend
npm install
```

### 2) Configure environment

```bash
copy .env.example .env.local
```

`NEXT_PUBLIC_API_URL` should point to backend API base URL including `/api`.

Example:

```env
NEXT_PUBLIC_API_URL=http://localhost:8000/api
```

### 3) Run dev server

```bash
npm run dev
```

Open `http://localhost:3000`.

## Scripts

- `npm run dev` - run local development server
- `npm run build` - production build
- `npm run start` - run production build locally
- `npm run lint` - ESLint
- `npm test` - run Vitest once
- `npm run test:watch` - run Vitest in watch mode
- `npm run test:e2e` - build standalone and run Playwright E2E on dedicated ports
- `npm run test:e2e:docs` - capture documentation screenshots

## API Contract Used by Frontend

- `POST {API_BASE}/extract`
  - request: multipart form with `file`
  - response: `{ data, scan_id, confidences, quality }`
- `POST {API_BASE}/jobs` → `202` job; `GET {API_BASE}/jobs/{id}` polled every 1.5 s;
  `POST {API_BASE}/jobs/{id}/cancel` on cancel/reset/new upload (`useBatchExtract`)
- `POST {API_BASE}/extract-batch` (legacy, no longer used by the UI)
  - request: multipart form with repeated `files`
  - response:
    `{ total, accepted_count, rejected_count, results }`
  - each `results[]` item contains:
    `{ index, filename, accepted, status, quality, data, confidences, scan_id, error_code, error_message }`
  - `status` is `extracted`, `rejected`, or `ocr_failed`
- `POST {API_BASE}/export`
  - request: `{ data: CCCDData, scan_id?: string }` JSON
  - response: Excel blob (`.xlsx`) with `Content-Disposition` filename

### Image quality precheck

`src/lib/quality.ts` performs a conservative browser-side precheck before upload:

- Hard reject: non-image file, very low resolution.
- Soft warnings: slightly low resolution, dark/bright image, glare.
- Backend remains the source of truth and adds real-mode CCCD card-presence
  checks through YOLO. UI shows per-image quality reasons in `BatchResultPanel`.

### Request reliability

The API client (`src/lib/api.ts`) wraps every request in `fetchWithTimeout`:

- **Timeout** via `AbortController` (default 30s; 120s for `/extract`;
  max(120s, 30s per file) for `/extract-batch`). On timeout it throws `APIError`
  with `code: "timeout"`.
- **Batch cancellation**: `useBatchExtract` aborts the previous `/extract-batch`
  request on re-upload, reset or unmount.
- **Caller cancellation**: `getScans` / `getScan` / `getRecords` accept an
  optional `AbortSignal`. The History/Records pages abort their fetch on unmount,
  so navigating away does not leak a pending request or update unmounted state.
  The caller signal is *combined* with the timeout signal (both stay active).
- Use `isAbortError(err)` to tell a caller-initiated cancellation apart from a
  real server/timeout error.

## Testing

```bash
npm test
```

## Source Layout

```text
frontend/
|- src/
|  |- app/                  # Next.js App Router pages
|  |- components/           # Upload, form, UI components
|  |- hooks/                # useExtractCCCD, useExportExcel
|  |- lib/                  # API client + Zod schemas
|  |- constants/
|  |- types/
|  `- __tests__/
|- public/
`- package.json
```
