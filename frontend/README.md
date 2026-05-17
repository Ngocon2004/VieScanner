# VieScanner Frontend

Next.js client for uploading CCCD images, reviewing OCR results, and exporting Excel.

## Features

- Drag-and-drop image upload + mobile camera capture
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

## API Contract Used by Frontend

- `POST {API_BASE}/extract`
  - request: multipart form with `file`
  - response: `{ data: CCCDData, confidences: Record<string, number> }`
- `POST {API_BASE}/export`
  - request: `CCCDData` JSON
  - response: Excel blob (`.xlsx`) with `Content-Disposition` filename

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
