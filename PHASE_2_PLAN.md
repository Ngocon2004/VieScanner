# Phase 2 — OCR thật (Plan chi tiết)

> Trạng thái: **Planning** (chưa code logic, chỉ scaffolding).
> Mục tiêu cuối: **Production-ready** pipeline OCR CCCD Việt Nam.
> Tham khảo: [denghwee/OCR_Vietnamese_Read_CCCD](https://github.com/denghwee/OCR_Vietnamese_Read_CCCD)

---

## 1. Pipeline kiến trúc

Mirror denghwee với một số điều chỉnh cho production VieScanner:

```
┌─────────────────┐
│ Ảnh CCCD upload │  (FastAPI /api/extract đã có)
└────────┬────────┘
         ↓
┌────────────────────────────┐
│ ① CardAligner (YOLO)       │  Detect 4 góc thẻ → perspective transform
│   model_crop.pt 6.2MB      │  Input: ảnh bất kỳ → Output: ảnh CCCD thẳng (BGR)
└────────┬───────────────────┘
         ↓
┌────────────────────────────┐
│ ② ImageCleaner (OpenCV)    │  Shadow removal + contrast + denoise + gauss blur
│   Pure CPU, no model       │  Input: BGR ảnh CCCD → Output: RGB ảnh sạch
└────────┬───────────────────┘
         ↓
┌────────────────────────────┐
│ ③ TextDetector (PaddleOCR) │  PP-OCRv5_server_det – detect bbox vùng text
│   ~50-100MB models         │  Input: ảnh → Output: List[bbox xmin,ymin,xmax,ymax]
└────────┬───────────────────┘
         ↓
┌────────────────────────────┐
│ ④ TextRecognizer (VietOCR) │  VGG-Transformer – nhận dạng tiếng Việt
│   ~100MB model             │  Input: ảnh + boxes → Output: List[str] (raw text)
└────────┬───────────────────┘
         ↓
┌────────────────────────────┐
│ ⑤ FieldExtractor (Rule)    │  Rule-based + regex thay vì BERT NER (denghwee dùng)
│   Pure Python              │  Input: text lines + bboxes → Output: CCCDData
└────────┬───────────────────┘
         ↓
┌────────────────────────────┐
│ ⑥ Postprocessor (Pydantic) │  Validate + normalize (đã có validators ở Phase 1)
└────────┬───────────────────┘
         ↓
   CCCDData JSON
```

### Khác biệt với denghwee
| Stage | Denghwee | VieScanner (planned) | Lý do |
|---|---|---|---|
| ⑤ Field extraction | BERT NER hoặc Ollama LLM | Rule-based regex + positional heuristics | CCCD layout cố định, không cần ML; nhanh, không cần train dataset, production-ready ngay |
| UI | Streamlit demo | Next.js production app (đã có) | Production app thay vì demo |
| Spelling correction | Có module riêng | Tích hợp vào FieldExtractor | Đơn giản hơn cho rule-based |

---

## 2. Stack & dependencies (Python 3.13)

### 2.1. Versions
```
torch==2.8.0  (CUDA 12.8 wheels; CUDA 12.9 backward compatible)
torchvision==0.23.0

ultralytics==8.3.208      # YOLO cho card alignment
paddlepaddle==3.2.0       # CPU build, hoặc paddlepaddle-gpu cho CUDA
paddleocr==3.2.0          # Text detection
vietocr==0.3.13           # Text recognition (cần install --no-deps)
opencv-python==4.12.0.88
opencv-python-headless==4.12.0.88  # cho server (no GUI)
pillow>=10.4              # vietocr pin pillow==10.2 → conflict với Python 3.13
numpy>=2.2,<3
```

### 2.2. Python 3.13 compat status

| Lib | Wheel cp313 win_amd64 | Note |
|---|---|---|
| paddlepaddle 3.2.0 | ✅ | Direct install OK |
| paddleocr 3.2.0 | ✅ | Pure Python wrapper |
| vietocr 0.3.13 | ⚠️ | Pin `pillow==10.2.0` (no cp313 wheel) → **cần `pip install vietocr --no-deps`** rồi install deps thủ công với `pillow>=10.4` |
| ultralytics 8.3.208 | ✅ | Tốt với Python 3.13 |
| torch 2.8.0 cu128 | ✅ | Wheel có sẵn cho cp313 |
| opencv-python 4.12+ | ✅ | OK |

**Risk mitigation cho vietocr**:
```bash
# Cài deps đúng version (drop pillow pin)
pip install einops==0.2.0 gdown==4.4.0 prefetch-generator==1.0.1 \
            imgaug==0.4.0 albumentations==1.4.2 lmdb scikit-image \
            "pillow>=10.4"
# Cài vietocr không kéo theo pillow cũ
pip install vietocr==0.3.13 --no-deps
```

### 2.3. CPU-first vs GPU
- Detect: `if torch.cuda.is_available(): device='cuda:0' else 'cpu'`
- Config env: `OCR_DEVICE=auto|cpu|cuda:0` (default `auto`)
- Mỗi stage (aligner/recognizer) đều cần truyền device

---

## 3. Sub-phases (estimate)

### Phase 2.0 — Scaffolding (1-2h) ⭐ NEXT
Không cần install ML stack. Tạo cấu trúc + interface + mock.

- [ ] **2.0.1** Tạo cấu trúc thư mục:
  ```
  backend/app/services/ocr/
    ├── __init__.py
    ├── pipeline.py          # OCRPipeline orchestrator
    ├── interfaces.py        # Protocol cho từng stage
    └── stages/
        ├── __init__.py
        ├── aligner.py       # CardAligner (Protocol + Mock)
        ├── cleaner.py       # ImageCleaner (Protocol + Mock)
        ├── detector.py      # TextDetector (Protocol + Mock)
        ├── recognizer.py    # TextRecognizer (Protocol + Mock)
        └── extractor.py     # FieldExtractor (Protocol + Mock)
  backend/weights/           # ML weights, ignore qua .gitignore
    └── model_crop.pt        # 6.2MB từ denghwee (sẽ download Phase 2.2)
  ```
- [ ] **2.0.2** Define `interfaces.py`:
  ```python
  class Aligner(Protocol): def align(self, img: np.ndarray) -> np.ndarray | None: ...
  class Cleaner(Protocol): def clean(self, img: np.ndarray) -> np.ndarray: ...
  class Detector(Protocol): def detect(self, img: np.ndarray) -> list[BBox]: ...
  class Recognizer(Protocol): def recognize(self, img: np.ndarray, boxes: list[BBox]) -> list[str]: ...
  class Extractor(Protocol): def extract(self, lines: list[TextLine]) -> CCCDData: ...
  ```
- [ ] **2.0.3** Mock implementations cho mỗi stage (chỉ return dữ liệu test)
- [ ] **2.0.4** `OCRPipeline` class: orchestrator nhận `Aligner, Cleaner, Detector, Recognizer, Extractor` qua DI
- [ ] **2.0.5** Config env:
  ```
  OCR_ENGINE=mock|real     # default mock
  OCR_DEVICE=auto|cpu|cuda:0
  OCR_MODEL_DIR=./models
  OCR_DEBUG_SAVE=false
  ```
- [ ] **2.0.6** Refactor `services/ocr_engine.py` → giờ wrap `OCRPipeline`
- [ ] **2.0.7** Smoke test: API `/api/extract` vẫn hoạt động với mock pipeline

**Verify**: `curl /api/extract` trả CCCDData (mock data); FE vẫn hoạt động.

---

### Phase 2.1 — ImageCleaner real (1-2h)
Pure OpenCV, no model — có thể làm ngay.

- [ ] **2.1.1** `pip install opencv-python-headless==4.12.0.88 numpy>=2.2`
- [ ] **2.1.2** Implement `RealImageCleaner` port từ denghwee `image_cleaner.py`:
  - Shadow removal: dilate + medianBlur background subtraction
  - Contrast: histogram-based auto adjustment
  - Smooth: GaussianBlur
- [ ] **2.1.3** Unit test với ảnh CCCD mẫu (input: file path → output: cleaned `np.ndarray`)
- [ ] **2.1.4** Config: `OCR_CLEANER=mock|real` (default `real`)

**Verify**: Save cleaned image ra `./output/cleaned_*.png`, eyeball check.

---

### Phase 2.2 — CardAligner real (2-3h)
Cần download model, install ultralytics.

- [ ] **2.2.1** `pip install ultralytics==8.3.208 torch==2.8.0 torchvision==0.23.0` (CPU; nếu có GPU dùng `--index-url https://download.pytorch.org/whl/cu128`)
- [ ] **2.2.2** Download `model_crop.pt` (6.2MB) từ denghwee:
  ```
  curl -L https://raw.githubusercontent.com/denghwee/OCR_Vietnamese_Read_CCCD/master/model/model_crop.pt -o backend/weights/model_crop.pt
  ```
- [ ] **2.2.3** Implement `RealCardAligner` (YOLO 4-corner detect + perspective warp):
  - Load `YOLO(model_path)` ở `__init__` (lazy via `lru_cache`)
  - `detect_corners()`: chọn confidence cao nhất cho mỗi corner class
  - `estimate_missing_corner()`: nội suy 1 góc thiếu (như denghwee)
  - `warp_perspective()`: cv2.getPerspectiveTransform + warp
- [ ] **2.2.4** Unit test với ảnh CCCD thật (cần user cung cấp 2-3 ảnh test)
- [ ] **2.2.5** Test fallback khi không detect đủ 4 góc → throw `OCRFailedError` với message rõ ràng
- [ ] **2.2.6** Add `expose_headers` cho debug image (optional)

**Verify**: Aligner output ảnh CCCD đã thẳng và crop sát viền.

**Risk**: Nếu ảnh test khác data train của denghwee → fail rate cao. Mitigation: prompt user upload lại với ảnh chụp thẳng.

---

### Phase 2.3 — TextDetector real (2-3h)
PaddleOCR cho detect text boxes.

- [ ] **2.3.1** `pip install paddlepaddle==3.2.0 paddleocr==3.2.0`
  - GPU: `pip install paddlepaddle-gpu==3.2.0 -f https://www.paddlepaddle.org.cn/whl/...`
  - First run sẽ auto-download `PP-OCRv5_server_det` (~50MB)
- [ ] **2.3.2** Implement `RealTextDetector`:
  - `detector = TextDetection(model_name="PP-OCRv5_server_det")`
  - `predict()` → list bbox (xmin, ymin, xmax, ymax) với padding 4px
- [ ] **2.3.3** Config: `OCR_DETECTOR_MODEL=PP-OCRv5_server_det|PP-OCRv5_mobile_det`
- [ ] **2.3.4** Test: hiển thị bbox lên cleaned image → eyeball

**Verify**: ~10-20 boxes cho mỗi CCCD, bao phủ đủ các trường.

**Risk**: PaddleOCR download model lần đầu chậm + cần kết nối Internet. Mitigation: pre-download trong Docker image cho prod.

---

### Phase 2.4 — TextRecognizer real (2-3h)
VietOCR cho nhận dạng tiếng Việt.

- [ ] **2.4.1** Install vietocr với workaround pillow:
  ```bash
  pip install einops==0.2.0 gdown prefetch-generator imgaug albumentations lmdb scikit-image "pillow>=10.4"
  pip install vietocr==0.3.13 --no-deps
  ```
- [ ] **2.4.2** Implement `RealTextRecognizer`:
  - Load `vgg_transformer` config + pretrained
  - Device: `cuda:0` hoặc `cpu` từ settings
  - `recognize(img, boxes)`: crop từng bbox, predict text, return list
- [ ] **2.4.3** Caching: lru_cache cho Predictor instance (load model ~5s)
- [ ] **2.4.4** Test với boxes từ Phase 2.3 + ảnh từ Phase 2.2

**Verify**: List text strings hợp lý cho mỗi field.

**Note**: VietOCR `vgg_seq2seq` config nhanh hơn (12ms) nhưng kém chính xác hơn `vgg_transformer` (86ms). Cho production-ready, ưu tiên transformer.

---

### Phase 2.5 — FieldExtractor real (3-4h)
Rule-based, không cần ML. Khá tricky vì CCCD có 2 layout (2016 và 2020).

- [ ] **2.5.1** Implement `RuleFieldExtractor`:
  - **Heuristic 1 (label-based)**: dòng có "Số/No.:" → next token là id; dòng có "Họ và tên/Full name:" → next line là name; v.v.
  - **Heuristic 2 (positional)**: nếu detector đã trả bbox, dùng y-coordinate để xếp thứ tự dòng từ trên xuống dưới.
  - **Heuristic 3 (regex)**:
    - `id_number`: `\d{12}` đầu tiên xuất hiện
    - `dob`: `(\d{1,2})[./](\d{1,2})[./](\d{4})`
    - `gender`: contain "Nam" / "Nữ"
  - **Fallback**: nếu không match, để trống và để user fill ở form FE
- [ ] **2.5.2** Spelling correction nhẹ:
  - "Việt Nam" có thể OCR ra "Viet Nam", "VietNam", "Việl Nam" → fuzzy match với từ điển nhỏ
  - "Nam" / "Nữ" → strict
  - Dùng `rapidfuzz` (lightweight, không cần ML)
- [ ] **2.5.3** Confidence scoring (Phase 2.10 trong roadmap):
  - Mỗi field gắn confidence dựa trên: regex match + spell correction distance + bbox confidence từ detector
  - Trả về `CCCDData` + `Dict[field, float]`
- [ ] **2.5.4** Update schema FE để hiển thị confidence indicator (Phase 3.x)
- [ ] **2.5.5** Test với 10 ảnh CCCD đa dạng (chụp thẳng, nghiêng, mờ, sáng tối)

**Verify**: Accuracy >= 90% cho id_number; >= 70% cho full_name; tổng end-to-end >= 60%.

**Risk**: Nếu rule-based không đủ accuracy → quay sang BERT NER (denghwee approach) hoặc gọi LLM (OpenAI/Ollama).

---

### Phase 2.6 — Orchestrator + DI (1-2h)
Wire tất cả stage thành `RealOCREngine`.

- [ ] **2.6.1** Update `services/ocr_engine.py`:
  ```python
  @lru_cache(maxsize=1)
  def _build_engine() -> OCREngine:
      if settings.ocr_engine == "real":
          return RealOCREngine(
              aligner=RealCardAligner(...),
              cleaner=RealImageCleaner(),
              detector=RealTextDetector(...),
              recognizer=RealTextRecognizer(...),
              extractor=RuleFieldExtractor(),
          )
      return MockOCREngine()
  ```
- [ ] **2.6.2** Lazy load models tại lần gọi đầu (không phải import time)
- [ ] **2.6.3** Health check `/health` thêm field `ocr_engine_ready: bool` để probe biết models đã load chưa
- [ ] **2.6.4** Graceful degradation: nếu 1 stage fail → return `OCRFailedError` với context cụ thể (`code: ocr_align_failed | ocr_detect_failed | ...`)

---

### Phase 2.7 — End-to-end test + tuning (3-5h)
Test với dataset ảnh CCCD thật.

- [ ] **2.7.1** Tạo `backend/tests/fixtures/cccd_samples/` (gitignore)
  - User cung cấp 5-10 ảnh CCCD test (mặt trước, đa dạng góc/sáng)
- [ ] **2.7.2** Script `scripts/eval_ocr.py`:
  - Input: ảnh + ground truth JSON
  - Output: accuracy per field + CER/WER metrics
- [ ] **2.7.3** Tune:
  - Image preprocessing params (Gaussian sigma, dilate kernel, etc.)
  - Bbox padding
  - VietOCR beamsearch on/off
  - Threshold confidence để reject low-quality results
- [ ] **2.7.4** Performance:
  - Time mỗi stage, identify bottleneck
  - Test GPU speedup
- [ ] **2.7.5** Docker image: pre-bake models vào image (PaddleOCR models + model_crop.pt + VietOCR weights)

---

## 4. Files sẽ tạo / sửa

### Backend
| File | Action | Phase |
|---|---|---|
| `backend/app/services/ocr/` (folder) | NEW | 2.0 |
| `backend/app/services/ocr/__init__.py` | NEW | 2.0 |
| `backend/app/services/ocr/interfaces.py` | NEW | 2.0 |
| `backend/app/services/ocr/pipeline.py` | NEW | 2.0 |
| `backend/app/services/ocr/stages/aligner.py` | NEW | 2.0, 2.2 |
| `backend/app/services/ocr/stages/cleaner.py` | NEW | 2.0, 2.1 |
| `backend/app/services/ocr/stages/detector.py` | NEW | 2.0, 2.3 |
| `backend/app/services/ocr/stages/recognizer.py` | NEW | 2.0, 2.4 |
| `backend/app/services/ocr/stages/extractor.py` | NEW | 2.0, 2.5 |
| `backend/app/services/ocr_engine.py` | REFACTOR | 2.6 |
| `backend/app/core/config.py` | EDIT (+ocr_engine, ocr_device, ocr_model_dir) | 2.0 |
| `backend/requirements.txt` | EDIT (+ stack ML) | 2.1-2.4 |
| `backend/weights/` (folder) | NEW | 2.2 |
| `backend/.gitignore` | EDIT (ignore models/*.pt) | 2.2 |
| `backend/scripts/eval_ocr.py` | NEW | 2.7 |
| `backend/tests/fixtures/cccd_samples/` | NEW | 2.7 |

### Frontend (tích hợp confidence)
| File | Action | Phase |
|---|---|---|
| `frontend/src/lib/schemas.ts` | EDIT (+confidence field optional) | 2.5 |
| `frontend/src/components/form/CCCDForm.tsx` | EDIT (highlight low-conf field) | 2.5 |

---

## 5. Risks & mitigation

| Risk | Severity | Mitigation |
|---|---|---|
| `vietocr` pin `pillow==10.2` không build trên Python 3.13 | High | Install với `--no-deps` + pillow >= 10.4 |
| `model_crop.pt` train trên data denghwee → fail với layout khác | Medium | Hỏi user xác nhận ảnh test, có thể retrain nếu cần |
| PaddleOCR + Paddle install size lớn (~500MB) + lần đầu chậm | Medium | Pre-bake trong Docker; cache wheel |
| GPU memory (3050 chỉ 4GB) | Medium | Dùng PP-OCRv5_**mobile**_det thay vì server; VietOCR seq2seq nếu cần |
| Accuracy rule-based extractor không đủ | Medium | Fallback BERT NER hoặc LLM extraction (denghwee approach) |
| User upload ảnh xấu (mờ/tối/cong) | Low | Trả error sớm với code `ocr_quality_low` |

---

## 6. Quick start cho session sau

Khi user muốn tiếp tục Phase 2, bắt đầu bằng:

1. **Confirm scope phiên sau**: làm Phase 2.0 (scaffolding, ~1-2h) hay Phase 2.0 + 2.1 (scaffolding + cleaner real)?
2. **Check disk space**: ML stack sẽ chiếm thêm ~2-3GB trên disk
3. **User chuẩn bị**: 3-5 ảnh CCCD test (có thể fake/template) cho Phase 2.2+

---

## Reference

- denghwee/OCR_Vietnamese_Read_CCCD: https://github.com/denghwee/OCR_Vietnamese_Read_CCCD
- PaddleOCR docs: https://github.com/PaddlePaddle/PaddleOCR
- VietOCR repo: https://github.com/pbcquoc/vietocr
- Ultralytics YOLO: https://github.com/ultralytics/ultralytics
