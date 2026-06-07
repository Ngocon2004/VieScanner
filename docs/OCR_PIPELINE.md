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
- `TextLine`: `text, bbox, recognizer_confidence`
- `ExtractionResult`: `fields` + `confidences`

Pipeline validates final fields through `CCCDData` Pydantic schema.

## QR Fast-Path (front-side chip CCCD)

Chip-based CCCD (2021+) embed a QR code on the front, encoding 7 pipe-separated
fields:

```text
<id number>|<old CMND>|<full name>|<DOB ddmmyyyy>|<gender>|<residence>|<issue date ddmmyyyy>
```

`app/services/ocr/qr.py` decodes it with `cv2.QRCodeDetector` (no extra
dependency, runs in both mock and real engines):

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

## Tuning Parameters

### QR

- `OCR_QR_ENABLED` (default `true`) — read the front-side QR before OCR.

### Aligner

- `OCR_ALIGNER_CONF_THRESHOLD`
- `OCR_ALIGNER_RETRY_CONF_THRESHOLDS_RAW`

Lower threshold can recover harder images but may add false corners.

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

### Extractor

- `OCR_EXTRACTOR_FUZZY_THRESHOLD`

## Debugging Workflow

Set `OCR_DEBUG_SAVE=true` to persist per-run artifacts:

- `01_input_bgr.png`
- `02_aligned_bgr.png`
- `03_cleaned.png`
- `04_detector_boxes.png`
- `05_result.json`

Output folder: `backend/debug_images/<timestamp>_<id>/`

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

### Grid search tuning

```bash
cd backend
venv\Scripts\python scripts\tune_ocr_grid.py <image_folder> --ground-truth <gt.json> --out scripts/tune_results.json
```

## Failure Modes

- `ocr_aligner_failed`: card corners not reliably detected.
- `ocr_detector_failed`: detector runtime/model issue.
- `ocr_recognizer_failed`: recognizer initialization/inference issue.
- `ocr_failed`: final fields cannot pass schema validation.

## Performance Notes

- Pipeline traces stage timing and reports bottleneck stage.
- `vgg_transformer` usually gives better accuracy but slower latency.
- `vgg_seq2seq` is faster and can be used for lightweight demo runs.

## Tuning Final Results (Phase 2.7)

After running the grid search with the ground truth dataset, the optimal parameters for the OCR pipeline have been selected. These settings balance execution speed with high field-level accuracy and are defined as the default in `app.core.config.py`.

**Optimal Configuration (Defaults):**
- `OCR_ALIGNER_CONF_THRESHOLD`: 0.25 (with retries down to 0.05)
- `OCR_CLEANER_SHADOW_KERNEL_SIZE`: 7
- `OCR_CLEANER_CLIP_HIST_PERCENT`: 1.0
- `OCR_DETECTOR_CONF_THRESHOLD`: 0.25
- `OCR_DETECTOR_PADDING`: 4
- `OCR_RECOGNIZER_BEAMSEARCH`: True
- `OCR_EXTRACTOR_FUZZY_THRESHOLD`: 80

**Accuracy Highlights (Benchmark on real images):**
- ID Number Accuracy: ~100%
- Full Name Accuracy: ~83.3%
- Pipeline Success Rate: The full pipeline (YOLO aligner -> Text detector -> Recognizer -> Extractor) performs reliably within acceptable margins for Demo purposes. Difficult images (e.g. heavily cropped, very bad lighting) will fail early at the Aligner stage.
