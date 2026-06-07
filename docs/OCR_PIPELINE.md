# OCR Pipeline (5 Stages)

This document explains the real OCR path used when `OCR_ENGINE=real`.

## Pipeline Summary

```text
Image bytes
  -> decode (OpenCV)
  -> Stage 1: RealCardAligner
  -> Stage 2: RealImageCleaner
  -> Stage 3: RealTextDetector
  -> Stage 4: RealTextRecognizer
  -> Stage 5: RealFieldExtractor
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

## Tuning Parameters

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
