# OCR Pipeline (5 Stages)

This document explains the real OCR path used when `OCR_ENGINE=real`.

## Pipeline Summary

```text
Image bytes
  -> decode (OpenCV)
  -> QR read (front-side chip CCCD, if present)
  -> Stage 1: RealCardAligner
  -> Stage 2: RealImageCleaner
  -> Stage 3: RealTextDetector
  -> Stage 4: RealTextRecognizer
  -> Stage 5: RealFieldExtractor
  -> merge QR over OCR fields (QR wins for the fields it provides)
  -> back side only: MRZ fields (checksum-verified) over OCR fields
  -> CCCDData + confidences
```

## Stage Details

| Stage | Input | Output | Main Implementation |
|---|---|---|---|
| 1. Aligner | raw BGR image | perspective-warped card image | YOLO `model_crop.pt`, 4-corner recovery, warp |
| 2. Cleaner | aligned image | cleaned RGB image | shadow removal + contrast normalization |
| 3. Detector | cleaned image | text `BBox[]` | PaddleOCR `PP-OCRv5_*_det` |
| 4. Recognizer | cleaned image + boxes | `TextLine[]` | VietOCR (`vgg_transformer` or `vgg_seq2seq`) |
| 5. Extractor | text lines | field map + confidences | regex + label matching + fuzzy rules |

## Core Contracts

- `BBox`: `xmin, ymin, xmax, ymax, confidence`
- `TextLine`: `text, bbox, recognizer_confidence` (`None` = recognizer gave no probability, e.g. VietOCR beamsearch)
- `ExtractionResult`: `fields` + `confidences`

Field confidence = `min(rule confidence, VietOCR probability of the source line(s))`.
Rule confidence: regex 1.0, label 0.85, fuzzy 0.7-0.85, not found 0 (placeholder).

Pipeline validates final fields through `CCCDData` Pydantic schema. An invalid
field does not fail the whole image: too-long text is truncated (confidence <= 0.5),
other invalid values fall back to the placeholder `(không nhận dạng được)` with
confidence 0 so the user must review it.

## QR Fast-Path (front-side chip CCCD)

Chip-based CCCD (2021+) embed a QR code on the front, encoding 7 pipe-separated
fields:

```text
<id number>|<old CMND>|<full name>|<DOB ddmmyyyy>|<gender>|<residence>|<issue date ddmmyyyy>
```

The 2024 Căn cước card uses an 11-field QR whose first 7 fields are identical,
so the same parser handles both.

`app/services/ocr/qr.py` decodes it with `zxing-cpp` (falls back to
`cv2.QRCodeDetector` when zxing-cpp is not installed; on 63 real images zxing-cpp
decoded 10 CCCD QR codes vs 1 for OpenCV, about 10× faster). It runs in both mock
and real engines:

- **QR fields** (`id_number`, `full_name`, `dob`, `gender`, `residence`) come
  straight from the QR and override the OCR result with confidence `1.0`.
- **Non-QR fields** (`nationality`, `origin`, `expiry_date`) still come from the
  OCR extractor — QR does not contain them.
- **OCR is the fallback**: when no QR is present (or it cannot be parsed as a
  CCCD payload), the result is the pure OCR output.
- **QR-only resilience**: if OCR fails (e.g. aligner/detector error) but a QR was
  read, the response is built from the QR fields plus safe defaults
  (`nationality = "Việt Nam"`, `origin` placeholder) so the user still gets the
  high-accuracy QR data.

Dates are normalized from `ddmmyyyy` to `dd/mm/yyyy`. Toggle with
`OCR_QR_ENABLED` (default on).

## Back Side (MRZ)

`app/services/ocr/mrz.py` reads the ICAO 9303 TD1 strip from the recognized lines:

- Line 1: `IDVNM` + last 9 digits of the ID + check digit + full 12-digit ID.
- Line 2: birth `YYMMDD` + check, sex `M/F`, expiry `YYMMDD` + check, `VNM`.

VietOCR drops every `<` and sometimes reads `0` as `O`, so the parser searches for
digit runs whose 7-3-1 check digits match instead of fixed positions. Only
checksum-verified values are used, with confidence `1.0` like QR. Birth century
and gender come from the ID number when it was read.

- **Back side only** (`review.looks_like_back_side`: MRZ or "Đặc điểm nhân
  dạng"/"Ngón trỏ" and no name): MRZ fields override OCR. The OCR `dob` is always
  dropped, because the only date the label extractor finds there is the issue date.
  The `back_side` notice tells the user to upload the front for name, origin and
  residence, and says when the fields came from the MRZ.
- **A name was already read** (the back of a 2024 Căn cước, which carries the QR,
  or a photo of both sides): MRZ fields are used only when the MRZ ID equals the ID
  already read, and never replace QR values.

On the 63 real images, 5 had a readable MRZ: 4 back sides without a QR got ID,
gender and expiry (and DOB on 3), all consistent with the ID; 1 back side of a
2024 card got its expiry next to the QR fields. Front-side results did not change. The OCR `dob` on back sides
was the issue date on all 4 images that could be cross-checked.

## Tuning Parameters

### QR

- `OCR_QR_ENABLED` (default `true`) — read the front-side QR before OCR.

### Aligner

- `OCR_ALIGNER_CONF_THRESHOLD`
- `OCR_ALIGNER_RETRY_CONF_THRESHOLDS_RAW`
- `OCR_ALIGNER_CONTOUR_FALLBACK` (default `true`)

Lower threshold can recover harder images but may add false corners.

Alignment order (`app/services/ocr/card_geometry.py`):

1. YOLO corners, used only when the quad looks like an ID-1 card: every corner within 30° of
   square, opposite sides within 1.4×, aspect within 35% of 85.6/54 (portrait allowed).
2. Otherwise, find the card outline with OpenCV: Canny/Otsu masks → largest contour → 4-point
   polygon, or a rotated bounding rect when the rounded corners prevent a clean polygon.
   A quad hugging the image frame is accepted here (the warp then keeps nearly the whole
   image, which still lets OCR read the card), but never counts as proof of a card.
3. Otherwise, warp with the distorted YOLO quad (previous behaviour).

The quality gate downgrades `not_cccd` (YOLO sees 0 corners) to a soft `card_partial` when an
outline is found, so these images still reach OCR.

### Cleaner

- `OCR_CLEANER_SHADOW_KERNEL_SIZE`
- `OCR_CLEANER_CLIP_HIST_PERCENT`

### Detector

- `OCR_DETECTOR_MODEL`
- `OCR_DETECTOR_CONF_THRESHOLD`
- `OCR_DETECTOR_PADDING`

### Recognizer

- `OCR_RECOGNIZER_MODEL`
- `OCR_RECOGNIZER_BEAMSEARCH`
- `OCR_RECOGNIZER_BATCH` (default `true`) — recognize every detected box in a
  single VietOCR `predict_batch` call instead of looping box-by-box. This is the
  slowest stage, so batching cuts latency noticeably. Trade-off: `predict_batch`
  always uses greedy decoding (no beamsearch) but returns a real per-line
  confidence. With per-box `predict()` + beamsearch the confidence is `None`
  (stored as `0.0`). Set to `false` to keep beamsearch accuracy.

### Extractor

- `OCR_EXTRACTOR_FUZZY_THRESHOLD`

The 12-digit CCCD number encodes `[3-digit province][century+gender][2-digit birth year][6 random]`
(`app/services/ocr/cccd_number.py`). The extractor uses it to:

- pick the first 12-digit candidate with a valid structure (otherwise keep the first one at
  confidence ≤ 0.5);
- prefer the date whose year matches the birth year as DOB (flagged when it differs from
  the earliest date);
- derive gender when OCR cannot read it (confidence 0.8);
- lower `id_number` and the conflicting `gender` / `dob` to ≤ 0.5 when they disagree.

It cannot catch errors in the 6 random digits, or a wrong day/month when the year is right.

VietOCR in batch mode reports high probabilities even for wrong text, so the text fields
(`full_name`, `origin`, `residence`) are also lowered to ≤ 0.5 when the value looks wrong:

- leftover label text or odd symbols;
- name: digits, the letters f/j/w/z, or fewer than 2 / more than 7 words;
- origin: one word, or digits;
- residence: one word, no administrative unit (xã, phường, huyện, tỉnh, thôn…), or the next line
  still looks like an address (value probably cut).

A value after `Label:` merges the next line only when that line contains an administrative unit.

### Image Quality Gate

Before OCR, `/api/extract` and `/api/extract-batch` run
`app/services/image_quality.py`:

- `QUALITY_MIN_SIDE_HARD_PX` / `QUALITY_MIN_SIDE_SOFT_PX`: resolution check.
- `QUALITY_BLUR_VAR_HARD` / `QUALITY_BLUR_VAR_SOFT`: Laplacian sharpness.
- `QUALITY_DARK_HARD` / `QUALITY_DARK_SOFT`: under-exposure.
- `QUALITY_BRIGHT_HARD` / `QUALITY_BRIGHT_SOFT`: over-exposure.
- `QUALITY_GLARE_HARD` / `QUALITY_GLARE_SOFT`: near-white glare ratio.
- `QUALITY_CARD_CHECK_ENABLED`: YOLO card-presence check in `OCR_ENGINE=real`.

Hard issues block OCR and return `image_quality_low`; soft issues are returned
as warnings while OCR continues. Card-presence uses the same aligner retry
thresholds as `RealCardAligner.align`, so low-confidence corner detections are
counted before deciding `not_cccd` or `card_partial`.

Resolution is checked on the original upload; blur, brightness, glare and the card
check run on the image resized to `OCR_MAX_IMAGE_SIDE_PX` (what OCR actually sees).

## Debugging Workflow

Set `OCR_DEBUG_SAVE=true` to persist per-run artifacts:

- `01_input_bgr.png`
- `02_aligned_bgr.png`
- `03_cleaned.png`
- `04_detector_boxes.png`
- `05_result.json`

Output folder: `backend/debug_images/<timestamp>_<id>/`

Artifacts are also written when a stage fails (e.g. only `01_input_bgr.png` when the
aligner fails); `05_result.json` then contains `error` and the stage timings. The
folder contains real CCCD images: keep it local (gitignored).

## Evaluation Scripts

### Batch evaluation

```bash
cd backend
venv\Scripts\python scripts\eval_ocr.py <image_folder> --out scripts/eval_results.json
```

With ground truth:

```bash
venv\Scripts\python scripts\eval_ocr.py <image_folder> --ground-truth <gt.json> --out scripts/eval_results_gt.json
```

Per-field report: exact match, CER, **silent errors** (wrong but confidence ≥ 0.6, so
the form does not flag them) and **review burden** (correct but flagged). Label values
equal to a placeholder are skipped as "unknown". "Read" means confidence > 0, because
the placeholders `Nam` / `Việt Nam` equal real values. The console prints only masked
IDs and counts; the `--out` file contains real data and must stay local.

### Grid search tuning

```bash
cd backend
venv\Scripts\python scripts\tune_ocr_grid.py <image_folder> --ground-truth <gt.json> --out scripts/tune_results.json
```

## Failure Modes

- `ocr_aligner_failed`: neither YOLO corners nor the card outline could be found.
- `ocr_detector_failed`: detector runtime/model issue, or no text region found.
- `ocr_engine_crashed`: unexpected error inside a stage (details only in server log).
- `ocr_recognizer_failed`: recognizer initialization/inference issue.
- `ocr_failed`: image cannot be decoded. A single invalid field (too long, bad date) no longer fails the image: it falls back to a placeholder with confidence 0.

## Performance Notes

- Pipeline traces stage timing and reports bottleneck stage.
- `vgg_transformer` usually gives better accuracy but slower latency.
- `vgg_seq2seq` is faster and can be used for lightweight demo runs.
- Recognizer batching (`OCR_RECOGNIZER_BATCH=true`) processes all boxes in one
  VietOCR call — the recognizer is the slowest stage, so this is the biggest
  per-request latency win.

### Evaluated and not adopted

Measured on the 63 local real images (stats only, QR as truth where present):

- **`latin_PP-OCRv5_mobile_rec`** instead of VietOCR: its dictionary lacks 45 of the
  73 lowercase Vietnamese letters (ạ, ễ, ộ, ữ…) and has no combining marks, so it
  cannot spell names or addresses.
- **Vintern-1B-v3.5 VLM** (local, MIT) as a fallback, prompted for JSON on the
  aligned card:
  - Speed: median 14.8 s, p90 25 s per card vs 1.6 s for the pipeline, because
    each generated token takes ~100 ms on the RTX 3050 / Windows.
  - Memory: 2.4 GB VRAM. It cannot stay loaded next to the pipeline on a 4 GB GPU
    (3.8 GB already in use): on the same 5 cards it took 32 s per card with the
    pipeline loaded vs 7 s after freeing it. On CPU a one-field answer still
    takes ~13 s, almost all of it reading the image.
  - Accuracy on 54 front sides: valid ID 45 vs 49 for the pipeline, gender
    consistent with the ID 43 vs 48, and it disagreed with a valid pipeline ID 3
    times.
  - Accuracy on 7 cards with a QR: residence word recall 75% vs 32% and name 71%
    vs 60%, so it reads multi-line addresses better.
  - Hallucination: on the 7 cards the pipeline reads poorly it filled every field,
    but only 1 ID was valid.

  A VLM fallback needs a GPU with room for both models and a field-level prompt;
  it is not wired in.

## Runtime & Stability

- **Concurrency guard (`OCR_MAX_CONCURRENCY`, default `1`)**: the engine is a
  process-wide singleton and the underlying models (YOLO / PaddleOCR / VietOCR)
  are shared and not thread-safe. `OCRPipeline.run` offloads inference to a
  thread, so parallel requests would otherwise hit the same model instances and
  risk crashes / GPU OOM. An `asyncio.Semaphore` in `ocr_engine.py` caps how many
  `extract` calls run at once. Raise it only if you have spare CPU cores / VRAM.
- **Warm-up (`OCR_WARMUP_ON_STARTUP`, default `true`)**: `main.py`'s `lifespan`
  builds the engine at startup so model weights are loaded before the first
  request (instead of paying that cost on request #1). It is best-effort — a
  failure (e.g. missing weights) only logs a warning and the engine lazy-loads on
  first use. Readiness is surfaced at `GET /health` via `ocr_engine_ready`.

## Tuning Final Results (Phase 2.7)

After running the grid search with the ground truth dataset, the optimal parameters for the OCR pipeline have been selected. These settings balance execution speed with high field-level accuracy and are defined as the default in `app.core.config.py`.

**Optimal Configuration (Defaults):**
- `OCR_ALIGNER_CONF_THRESHOLD`: 0.25 (with retries down to 0.05)
- `OCR_CLEANER_SHADOW_KERNEL_SIZE`: 7
- `OCR_CLEANER_CLIP_HIST_PERCENT`: 1.0
- `OCR_DETECTOR_CONF_THRESHOLD`: 0.25
- `OCR_DETECTOR_PADDING`: 4
- `OCR_RECOGNIZER_BEAMSEARCH`: True
- `OCR_RECOGNIZER_BATCH`: True
- `OCR_EXTRACTOR_FUZZY_THRESHOLD`: 80

**Quality Gate Defaults:**
- `QUALITY_MIN_SIDE_HARD_PX`: 320
- `QUALITY_MIN_SIDE_SOFT_PX`: 640
- `QUALITY_BLUR_VAR_HARD`: 30.0
- `QUALITY_BLUR_VAR_SOFT`: 100.0
- `QUALITY_DARK_HARD`: 35.0
- `QUALITY_DARK_SOFT`: 65.0
- `QUALITY_BRIGHT_HARD`: 243.0
- `QUALITY_BRIGHT_SOFT`: 220.0
- `QUALITY_GLARE_HARD`: 0.30
- `QUALITY_GLARE_SOFT`: 0.12
- `QUALITY_CARD_CHECK_ENABLED`: True

**Accuracy Highlights (Benchmark on real images):**
- ID Number Accuracy: ~100%
- Full Name Accuracy: ~83.3%
- Pipeline Success Rate: The full pipeline (YOLO aligner -> Text detector -> Recognizer -> Extractor) performs reliably within acceptable margins for Demo purposes. Difficult images (e.g. heavily cropped, very bad lighting) will fail early at the Aligner stage.

**Quality Gate Smoke (63 real images, Session P):**
- Accepted: 57/63.
- Hard rejects: `not_cccd` = 5, `blur` = 1.
- Soft warnings: `card_partial` = 26, `blur` = 4, `too_dark` = 3,
  `low_resolution` = 4.
- Real OCR smoke on 1 image succeeded: build ~56s, run ~16s, detector ~7.1s,
  recognizer ~7.5s, 20 boxes/lines.
