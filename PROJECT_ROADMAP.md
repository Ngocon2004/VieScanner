# VieScanner — Project Roadmap

> **Mục tiêu**: Đồ án sinh viên năm 4 (solo, không deadline).
> **Tham khảo chi tiết Phase 2**: [PHASE_2_PLAN.md](./PHASE_2_PLAN.md)
> **Ký hiệu task**: `✅` = đã hoàn thành, `⏳` = đang chờ hoàn thành.

---

## 🎯 Định hướng tổng thể

VieScanner là **hệ thống OCR CCCD Việt Nam → Excel**. Với scope đồ án, lộ trình tập trung vào 3 trụ:

1. **Core feature hoạt động** — OCR thật accuracy đủ tốt để demo.
2. **UI/UX đẹp** — thuyết phục hội đồng / người chấm.
3. **Documentation + present** — README, kiến trúc, screenshots, video demo.

**SKIP** với scope đồ án:
- ❌ GDPR / NĐ 13/2023 audit log
- ❌ OAuth / social login / multi-tenant auth UI đầy đủ
- ❌ Rate limit, security headers (CSP/HSTS)
- ❌ Sentry, PostHog, monitoring stack
- ❌ NFC chip reading, MRZ, watermark detection
- ❌ B2B bulk API, webhooks
- ❌ Multi-region deployment, k8s

Phần backend database + JWT cơ bản đã triển khai xong (xem `DATABASE_ROADMAP.md`).

---

## 📊 Trạng thái hiện tại

| Phase | Mô tả | Status |
|---|---|---|
| **Phase 0** | Quick Wins (favicon, gitignore, lint fix) | ✅ Done |
| **Phase 1 BE** | Logging, exception handlers, validators, DI | ✅ Done |
| **Phase 1 FE** | Strict TS, zod, hooks, error.tsx/loading.tsx | ✅ Done |
| **Phase 2.0** | OCR scaffolding (interfaces + mocks + pipeline) | ✅ Done |
| **Phase 2.1** | RealImageCleaner (OpenCV) | ✅ Done |
| **Phase 2.2** | RealCardAligner (YOLO) | ✅ Done |
| **Phase 2.3** | RealTextDetector (PaddleOCR) | ✅ Done |
| **Phase 2.4** | RealTextRecognizer (VietOCR) | ✅ Done |
| **Phase 2.5** | RealFieldExtractor (rule-based) | ✅ Done |
| **Phase 2.7** | Tuning với ảnh CCCD thật | ⏳ In progress (đã benchmark 63 ảnh thật, chờ ground-truth để chốt accuracy) |
| **Phase 3*** | UX polish (selective) | ✅ Done (selective) |
| **Phase 6*** | Testing (selective) | ✅ Done (selective) |
| **Sprint DB** | Backend database layer (SQLAlchemy/Alembic/JWT API/history) | ✅ Done |
| **Documentation** | README final, screenshots, demo video | ⏳ In progress (README/docs kỹ thuật đã xong; còn screenshots + video + slide) |

\* Cho đồ án chỉ làm subset.

---

## 🛣️ Lộ trình chi tiết (chia theo Sprint)

> Mỗi "Sprint" = 1-2 session làm việc (~2-4h). Sắp xếp theo critical path.

### **Sprint A — Phase 2.2: CardAligner real** (Ưu tiên #1)

**Mục tiêu**: Detect 4 góc CCCD bằng YOLO + perspective warp thành ảnh thẳng.

**Tasks**:
- ✅ Install `ultralytics 8.3.208` + `torch 2.8.0` (CPU; GPU optional cho RTX 3050)
  - Lưu ý: torch+CUDA ~2GB disk
  - `pip install ultralytics==8.3.208 torch==2.8.0 torchvision==0.23.0`
  - Cho GPU: `pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128`
- ✅ Download `model_crop.pt` (6.2MB) từ denghwee
  - `curl -L https://raw.githubusercontent.com/denghwee/OCR_Vietnamese_Read_CCCD/master/model/model_crop.pt -o backend/weights/model_crop.pt`
- ✅ Implement `RealCardAligner` trong `stages/aligner.py`:
  - Load `YOLO(model_path)` lazy (lru_cache)
  - Detect 4 corner classes: `top_left, top_right, bot_right, bot_left`
  - `estimate_missing_corner` nếu thiếu 1 góc (linear interpolation)
  - `cv2.getPerspectiveTransform` + `cv2.warpPerspective`
  - Raise `OCRStageError("aligner", ...)` nếu thiếu >1 góc
- ✅ Update `_build_real_pipeline` dùng `RealCardAligner`
- ✅ Test: chuẩn bị 2-3 ảnh CCCD test, eyeball aligned output

**Definition of Done**:
- Pipeline với aligner thật + cleaner thật + mock detector/recognizer/extractor chạy được
- Aligned image lưu vào debug folder, thấy CCCD được crop thẳng

**Risks**:
- ⚠️ Model_crop.pt train trên data denghwee, có thể fail với ảnh chụp khác. Mitigation: prompt user upload ảnh tương tự test set.

**Estimate**: 2-3h

---

### **Sprint B — Phase 2.3: TextDetector real**

**Mục tiêu**: Dùng PaddleOCR PP-OCRv5_server_det để detect bbox vùng text.

**Tasks**:
- ✅ Install `paddlepaddle 3.2.0` + `paddleocr 3.2.0`
  - `pip install paddlepaddle==3.2.0 paddleocr==3.2.0`
  - GPU variant: `paddlepaddle-gpu`
  - First run sẽ auto-download `PP-OCRv5_server_det` (~50MB)
- ✅ Implement `RealTextDetector` trong `stages/detector.py`:
  - `detector = TextDetection(model_name="PP-OCRv5_server_det")`
  - `predict()` → list `BBox` với padding 4px
  - Sort bbox theo y-coordinate (top to bottom)
- ✅ Config: `OCR_DETECTOR_MODEL=PP-OCRv5_server_det|PP-OCRv5_mobile_det`
  - Mobile nhanh hơn nhưng accuracy thấp hơn
- ✅ Test: detect bbox trên ảnh cleaned từ Sprint A, eyeball bbox phủ đủ text

**Definition of Done**:
- Detect được ~10-20 bbox cho mỗi CCCD
- Bbox phủ đủ các trường (id, name, dob, gender, ...)

**Risks**:
- ⚠️ Download model lần đầu cần Internet. Mitigation: pre-bake vào Docker.
- ⚠️ Server model ~250MB. Mobile variant nhỏ hơn (~50MB).

**Estimate**: 2-3h

---

### **Sprint C — Phase 2.4: TextRecognizer real**

**Mục tiêu**: Dùng VietOCR VGG-Transformer để recognize text từng bbox.

**Tasks**:
- ✅ Install VietOCR với workaround `pillow` pin:
  ```bash
  pip install einops==0.2.0 gdown prefetch-generator imgaug \
              albumentations lmdb scikit-image "pillow>=10.4"
  pip install vietocr==0.3.13 --no-deps
  ```
- ✅ Implement `RealTextRecognizer` trong `stages/recognizer.py`:
  - Load `Cfg.load_config_from_name('vgg_transformer')`
  - `config['cnn']['pretrained'] = True`
  - `config['predictor']['beamsearch'] = True`
  - Device: từ `settings.ocr_device` (`auto` → detect cuda)
  - Crop bbox từ image → PIL → `predictor.predict(crop)`
  - Trả về `list[TextLine]` với confidence
- ✅ Lazy load Predictor (lru_cache, ~5s khởi tạo)
- ✅ Test: recognize text trên bbox từ Sprint B → eyeball string đúng

**Definition of Done**:
- Đọc được text tiếng Việt có dấu (NGUYỄN, VĂN A, Bến Nghé, ...)
- Đọc được số (12 digit CCCD, date)

**Risks**:
- ⚠️ VietOCR confidence không expose direct → cần workaround hoặc fallback 0.9 default
- ⚠️ VGG-Transformer chậm (~86ms/box) → 20 box = 1.7s. Cân nhắc `vgg_seq2seq` nếu cần nhanh hơn.

**Estimate**: 2-3h

---

### **Sprint D — Phase 2.5: RuleFieldExtractor**

**Mục tiêu**: Rule-based extractor parse list text → CCCDData. Đây là phần "thông minh" của pipeline.

**Tasks**:
- ✅ Install `rapidfuzz` (fuzzy matching, lightweight): `pip install rapidfuzz`
- ✅ Implement `RealFieldExtractor` trong `stages/extractor.py`:
  - **Heuristic 1 (label-based)**:
    - Tìm dòng chứa "Số/No.:" → next 12-digit là `id_number`
    - "Họ và tên/Full name:" → next non-empty line là `full_name`
    - "Ngày sinh/Date of birth:" → next dd/mm/yyyy là `dob`
    - v.v.
  - **Heuristic 2 (positional)**: nếu không có label, dùng y-coordinate xếp dòng từ trên xuống, map theo thứ tự CCCD layout 2020/2016.
  - **Heuristic 3 (regex)**:
    - `id_number`: regex `\d{12}` đầu tiên
    - `dob`: regex `(\d{1,2})[./](\d{1,2})[./](\d{4})`
    - `gender`: contain "Nam" / "Nữ"
  - **Spelling correction**:
    - "Việt Nam": fuzzy match với "Viet Nam", "VietNam", "Việl Nam"
    - "Nam" / "Nữ": strict (vì ngắn, dễ confuse)
  - **Confidence scoring**:
    - regex match = 1.0
    - fuzzy match >85 = 0.9
    - positional only = 0.6
    - không tìm thấy = 0.0 (để field rỗng, user fill)
- ✅ Update `_build_real_pipeline` dùng `RealFieldExtractor`
- ✅ Test: end-to-end với 3-5 ảnh CCCD

**Definition of Done**:
- Pipeline full real (cleaner+aligner+detector+recognizer+extractor) hoạt động
- Output `CCCDData` với accuracy >= 80% trên ảnh test

**Risks**:
- ⚠️ Layout CCCD 2016 và 2020 khác nhau → cần handle cả 2
- ⚠️ Rule-based có thể fail với ảnh OCR ra text scrambled → fallback positional

**Estimate**: 3-4h

---

### **Sprint E — Phase 2.7: Tuning + test với ảnh thật**

**Mục tiêu**: Đạt accuracy đủ tốt để demo (>=80% per field, >=60% end-to-end perfect).

**Tasks**:
- ✅ User chuẩn bị 5-10 ảnh CCCD test (mặt trước, đa dạng góc/sáng) — đã có dataset 63 ảnh thật (`D:\\Nam4\\Web_New\\Data_CCCD_5.26`).
  - Tip: dùng CCCD của bạn + bạn bè (xin phép), hoặc generate template từ ảnh public
  - **Lưu ý**: KHÔNG commit ảnh CCCD thật vào git (xem .gitignore)
- ✅ Tạo `backend/tests/fixtures/cccd_samples/` (gitignore)
- ✅ Script `backend/scripts/eval_ocr.py`:
  - Input: folder ảnh + ground truth JSON
  - Output: accuracy per field + CER/WER + per-image error report
- ⏳ Tune parameters + chốt config cuối bằng ground-truth:
  - `RealImageCleaner`: shadow_kernel_size, clip_hist_percent
  - `RealTextDetector`: confidence threshold, padding
  - `RealTextRecognizer`: beamsearch on/off
  - `RealFieldExtractor`: fuzzy threshold
  - ✅ Progress: đã benchmark aligner threshold/retry trên 63 ảnh thật (32/63 → 39/63 OK).
  - ⏳ Chạy grid-search đầy đủ với ground-truth thật để chốt accuracy cuối.
  - ⏳ Chốt bộ config mặc định cho demo và cập nhật report cuối vào docs.
- ✅ Expose tuning knobs qua env + `eval_ocr.py` CLI overrides để tune nhanh theo batch ảnh.
- ✅ Thêm `backend/scripts/tune_ocr_grid.py` để grid-search nhiều config và rank best config theo ground-truth.
- ✅ Performance: time mỗi stage, log bottleneck
- ✅ Add `OCR_DEBUG_SAVE=true` flag → save aligned/cleaned/annotated images cho debug
- ✅ Bonus: confidence per field → return JSON `{ data: {...}, confidences: {...} }`

**Definition of Done**:
- 5/5 ảnh test trả về `CCCDData` không lỗi
- Accuracy `id_number` >= 90%, `full_name` >= 80%, others >= 70%

**Estimate**: 3-5h

---

### **Sprint F — Phase 3: UX Polish (selective cho đồ án)**

**Mục tiêu**: UI thuyết phục hội đồng.

**Tasks** (đã sắp xếp theo impact):
- ✅ **3.1 Drag & drop upload** — show thay vì chỉ click button
  - Dùng React DnD events hoặc react-dropzone (nhẹ)
- ✅ **3.8 Toast notifications** — thay `alert()` xấu xí
  - Thư viện: `sonner` (nhẹ, đẹp, được Vercel khuyến nghị)
- ✅ **3.9 Skeleton loading** — thay text "Đang xử lý..."
  - Skeleton component cho `CCCDForm` khi loading
- ✅ **3.11 Validation realtime form** — show error ngay khi user nhập sai
  - Tích hợp với zod schema đã có
  - Highlight field invalid (border đỏ)
- ✅ **Confidence indicator** — hiển thị màu (xanh/vàng/đỏ) cạnh mỗi field theo confidence từ BE
  - Auto-focus vào field confidence thấp nhất
- ✅ **3.7 Responsive mobile** — test trên Chrome devtools mobile
  - Hiện đã có Tailwind responsive, cần verify
- ✅ **Camera capture (mobile)** — bonus, dùng `<input type="file" accept="image/*" capture="environment">`

**Skip** (không cần cho đồ án):
- ❌ 3.2 Paste from clipboard
- ❌ 3.3 Image crop tool
- ❌ 3.4 Multi-image batch
- ❌ 3.5 Mặt sau CCCD
- ❌ 3.6 Dark mode
- ❌ 3.10 i18n VI/EN
- ❌ 3.13 Accessibility advanced

**Definition of Done**:
- UI có 5+ features visual: drag-drop, toast, skeleton, validation, confidence
- Test trên mobile viewport OK

**Estimate**: 4-6h

---

### **Sprint G — Phase 6: Testing (selective cho đồ án)**

**Mục tiêu**: Có test để chứng minh chất lượng code khi present.

**Backend**:
- ✅ Setup `pytest` + `pytest-asyncio` + `httpx`
  - Đã có httpx; thêm pytest
- ✅ `tests/test_schemas.py` — test Pydantic validators (id_number regex, date format, gender enum)
- ✅ `tests/test_image_validation.py` — test validate_image_bytes (mime, magic bytes, size)
- ✅ `tests/test_api.py` — TestClient integration:
  - GET /health
  - POST /api/extract (mock engine)
  - POST /api/export (valid + invalid)
- ✅ `tests/test_ocr_pipeline.py` — pipeline với mock stages
- ✅ Coverage report: `pytest --cov=app` (target ~70%)

**Frontend**:
- ✅ Setup `vitest` + `@testing-library/react`
- ✅ `__tests__/CCCDForm.test.tsx` — render + edit + submit
- ✅ `__tests__/useExtractCCCD.test.ts` — hook state machine + race condition
- ✅ `__tests__/api.test.ts` — API error handling + Content-Disposition parse

**E2E (optional)**:
- ⏳ `playwright` — 1 test scenario: upload → check form → export

**Definition of Done**:
- Backend ~10 test cases pass
- Frontend ~5 test cases pass
- `npm test` và `pytest` chạy clean

**Estimate**: 4-6h

---

### **Sprint H — Documentation + Demo prep** (Ưu tiên cuối)

**Mục tiêu**: Tài liệu để present + nộp đồ án.

**Tasks**:
- ✅ **README.md root** — viết lại đầy đủ:
  - Mô tả project + use case
  - Demo screenshot/GIF
  - Tech stack với badges
  - Quick start (setup + run)
  - Project structure tree
  - Architecture diagram (Excalidraw/draw.io)
  - Features list
  - Roadmap / future work
  - License + author
- ✅ **README backend** — setup instructions chi tiết:
  - Python version, venv creation
  - Install deps (lưu ý vietocr `--no-deps`)
  - Download models
  - Env vars
  - Run dev + tests
- ✅ **README frontend** — Next.js setup, env vars
- ✅ **`docs/ARCHITECTURE.md`** — sơ đồ pipeline + sequence diagram
- ✅ **`docs/OCR_PIPELINE.md`** — giải thích chi tiết 5 stage (cho thuyết trình)
- ⏳ Screenshots:
  - Upload page
  - Form sau OCR
  - Excel output mở trong Excel
  - DevTools network tab (show API call)
- ⏳ **Demo video 2-3 phút** (screencast)
  - Upload ảnh CCCD → wait OCR → edit → export Excel → open in Excel
- ⏳ **Slide thuyết trình** (10-15 slides):
  - Problem statement
  - Solution / pipeline architecture
  - Tech stack
  - Demo (live hoặc video)
  - Challenges + how solved
  - Future work
  - Q&A

**Definition of Done**:
- README đẹp, ai clone về cũng setup được
- 1 video demo runable
- 1 bộ slide hoàn chỉnh

**Estimate**: 2-3h (không tính làm slide)

---

## 🎁 Optional Sprints (nếu còn thời gian)

### **Sprint I — Dockerize**

- ⏳ `backend/Dockerfile` (multi-stage, slim Python + ML deps)
- ⏳ `frontend/Dockerfile` (Next.js standalone output)
- ⏳ `docker-compose.yml` — backend + frontend + nginx
- ⏳ README có "Run with Docker" section

**Estimate**: 3-4h

### **Sprint J — Performance**

- ⏳ Image resize trước OCR (giảm RAM nếu ảnh > 2000px)
- ⏳ Cache OCR result theo image hash (tránh OCR lại)
- ⏳ Client-side image compression (`browser-image-compression`)
- ⏳ Bundle analyzer FE → cắt dependency thừa

**Estimate**: 3-4h

### **Sprint K — Mặt sau CCCD**

- ⏳ Add mặt sau detector + OCR
- ⏳ Schema: `cccd_back_data` (ngày cấp, nơi cấp, đặc điểm nhân dạng)
- ⏳ UI 2-step upload (mặt trước → mặt sau)

**Estimate**: 4-6h

---

## ⏱️ Tổng estimate

| Khối | Sprint | Estimate |
|---|---|---|
| **Core OCR** | A, B, C, D, E | 12-18h |
| **UX Polish** | F | 4-6h |
| **Testing** | G | 4-6h |
| **Documentation** | H | 2-3h |
| **Total MUST-HAVE** | | **~22-33h** |
| **Optional** | I, J, K | 10-14h |

**Cho đồ án solo, không deadline**: phân thành 8-12 session ~2-3h mỗi session, tổng ~3-4 tuần làm việc nhẹ nhàng (vài giờ/tuần) hoặc 1-2 tuần nếu intense.

---

## 🚦 Critical path (thứ tự bắt buộc)

```
Phase 2.2 (Aligner) ──┐
                      ├──> Phase 2.3 (Detector) ──> Phase 2.4 (Recognizer) ──> Phase 2.5 (Extractor) ──> Phase 2.7 (Tuning) ──> Phase 3 (UX) ──> Phase 6 (Tests) ──> Documentation ──> Demo
Phase 2.1 (Cleaner) ──┘                                                                                       │
                                                                                                              └──> Có thể start Phase 3 song song nếu busy
```

**Lưu ý**:
- Phase 2.7 (Tuning) cần ảnh CCCD thật — chuẩn bị từ sớm.
- Phase 3 (UX) có thể chạy **song song** với Phase 2.4-2.5 vì độc lập.
- Phase 6 (Tests) làm sau cùng để tránh sửa test khi đổi code.

---

## 🤔 Decision points

Các quyết định bạn cần làm khi đến từng Sprint:

| Sprint | Decision | Options |
|---|---|---|
| A (Aligner) | CPU hay GPU? | GPU nhanh hơn (~3-5x). RTX 3050 4GB OK. Code đã `OCR_DEVICE=auto`. |
| B (Detector) | Server model hay Mobile? | Server: chính xác hơn, chậm (~250MB). Mobile: ngược lại (~50MB). |
| C (Recognizer) | Transformer hay Seq2Seq? | Transformer chính xác hơn (86ms). Seq2Seq nhanh hơn (12ms). |
| D (Extractor) | Rule-based hay LLM? | Rule (recommended cho đồ án). LLM nếu rule fail và có OpenAI key/Ollama. |
| F (UX) | Toast lib nào? | `sonner` (recommend) vs `react-hot-toast`. |
| G (Tests) | Có cần E2E Playwright? | Optional. Backend pytest + Frontend vitest đã đủ. |

---

## 📝 Notes cho session sau

**Khi quay lại:**
1. Đọc lại file này (`PROJECT_ROADMAP.md`) → biết đang ở đâu
2. Đọc [PHASE_2_PLAN.md](./PHASE_2_PLAN.md) nếu vào sub-phase 2.x
3. `cd backend && venv\Scripts\activate.bat && uvicorn main:app --reload` để khởi động dev
4. `cd frontend && npm run dev` cho FE
5. Update status table ở mục "📊 Trạng thái hiện tại" mỗi khi xong 1 phase

**Tips**:
- Commit thường xuyên (mỗi sprint xong → 1 commit)
- Khi gặp bug, log lại trong commit message để demo "đã giải quyết X bug" khi present
- Lưu screenshot quá trình debug để show "before / after" trong slide
- Nếu ảnh CCCD thật không đủ, dùng template fake hoặc public sample (đảm bảo không vi phạm PII).

---

## 🆘 Khi bị stuck

| Vấn đề | Lý do thường gặp | Cách giải quyết |
|---|---|---|
| `pip install paddlepaddle` fail | Python 3.13 hoặc Windows path quá dài | Check classifier trên PyPI, dùng wheel cp313-win_amd64 |
| `pip install vietocr` fail (pillow) | Pillow 10.2 không có cp313 wheel | Dùng `--no-deps` + install deps thủ công |
| YOLO không detect 4 góc | Ảnh quá nghiêng / mờ | Tăng `img_size`, hoặc retrain model với dataset của bạn |
| VietOCR nhận text sai dấu | Ảnh quá nhỏ / blur | Tăng bbox padding, hoặc cleaner mạnh hơn |
| API trả 422 validation | OCR ra dữ liệu sai format | Soft mode: chỉ warn, không fail (đổi schema thành Optional) |
| GPU out of memory | Model quá lớn | Dùng PP-OCRv5_mobile_det, hoặc `vgg_seq2seq` |
| Build size frontend lớn | Tailwind purge sai | Bundle analyzer: `npm run build -- --analyze` |

---

**Last updated**: Session 15 (sync roadmap sau khi hoàn tất và gom DB layer về `app/db`).
- Hoàn tất roadmap database (xem `DATABASE_ROADMAP.md`): DB-A -> DB-G đều Done.
- Gom toàn bộ DB-related code vào `backend/app/db/`:
  - ORM models: `app/db/models/*`
  - DB repositories: `app/db/repositories/*`
  - Alembic config + migrations: `app/db/alembic.ini`, `app/db/migrations/*`
- Cập nhật import toàn backend/test theo namespace mới `app.db.*`.
- Verify sau refactor: `pytest` backend pass **25 tests**, Alembic migrate thành công với `-c app/db/alembic.ini`.

**Session 14**: sync toàn bộ roadmap theo trạng thái code hiện tại.
- Đồng bộ checklist Sprint A-D:
  - Tick done toàn bộ task Phase 2.2 → 2.5 (install, implement, wiring pipeline, test smoke/end-to-end).
  - Giữ trạng thái tổng quan nhất quán với bảng phase (`Phase 2.2/2.3/2.4/2.5 = ✅ Done`).
- Làm rõ phần còn lại cần làm:
  - Sprint E: còn bước chốt config cuối bằng ground-truth + report accuracy cuối.
  - Sprint H: còn screenshots, video demo, slide thuyết trình.
  - Sprint G optional: Playwright E2E.
- Rà lại roadmap để chỉ còn các checkbox chưa tick thuộc đúng các phần pending/optional.

**Session 13**: Documentation sprint tiếp theo.
- Hoàn thiện tài liệu nền tảng:
  - Viết lại `README.md` root theo trạng thái hiện tại (flow, quick start, test, docs links).
  - Thêm `backend/README.md` (setup Python/venv/deps, real OCR install notes, eval/tuning scripts).
  - Thay `frontend/README.md` template bằng hướng dẫn project thật (env, run, test, API contract).
  - Tạo `docs/ARCHITECTURE.md` và `docs/OCR_PIPELINE.md` phục vụ thuyết trình.
- Đồng bộ roadmap:
  - Đánh dấu done các task tài liệu đã hoàn thành trong Sprint H.
  - Cập nhật trạng thái Documentation từ `Pending` -> `In progress`.

**Session 12**: Roadmap sync sau benchmark ảnh thật.
- Đồng bộ roadmap: Phase 2.7 chuyển sang trạng thái "đã benchmark ảnh thật, chờ ground-truth để chốt accuracy".
- Chạy benchmark trên dataset thật 63 ảnh (`D:\\Nam4\\Web_New\\Data_CCCD_5.26`): baseline `32/63` OK (50.8%), lỗi chủ yếu `ocr_aligner_failed`.
- Tuning aligner thực tế:
  - `aligner_conf=0.10`: `38/63` OK (60.3%).
  - Aligner retry (mặc định `0.25 -> 0.15 -> 0.10 -> 0.05`): `39/63` OK (61.9%).
  - Retry tới `0.10` (không xuống `0.05`): `38/63` OK (60.3%) với chất lượng field cân bằng hơn.
- Thêm aligner retry thresholds trong config/env + wiring vào real pipeline.
- Sinh artifact local cho vòng refine tiếp theo: `scripts/failed_images_retry_upto_0_10.txt`, `scripts/ground_truth.seed.from_align_0_1.json`.
- Thêm ignore cho artifact có thể chứa PII trong `backend/.gitignore`.
- Thêm script `backend/scripts/tune_ocr_grid.py`: chạy grid-search nhiều tham số OCR và rank cấu hình tốt nhất theo ground-truth.
- Phase 2.7: thêm `run_with_trace()` + `PipelineTrace` trong OCR pipeline để đo thời gian từng stage và log bottleneck.
- Thêm `OCR_DEBUG_SAVE=true` để lưu artifact debug (`input/aligned/cleaned/detector_boxes/result.json`) theo từng run.
- Nâng cấp `backend/scripts/eval_ocr.py`: hỗ trợ ground-truth JSON, báo cáo accuracy per-field + CER/WER + mismatch chi tiết, và override tham số tuning qua CLI.
- Bổ sung fixtures mẫu `tests/fixtures/cccd_samples/` (`.gitkeep`, `README.md`, `ground_truth.template.json`) và chặn commit ảnh thật bằng `.gitignore`.
- Phase 3.7: hoàn thiện responsive mobile cho page/upload/form (giảm rủi ro overflow ở màn hẹp 320px, cải thiện wrapping cho label/confidence badge, request_id `break-all`).
- Verify frontend: `cd frontend && npm test` (**12 passed**), `npm run lint`, `npm run build` đều clean.
- Phase 6 frontend: setup `vitest` + testing-library, thêm `CCCDForm.test.tsx`, `useExtractCCCD.test.ts`, `api.test.ts`.
- Coverage backend: `cd backend && .\\venv\\Scripts\\python -m pytest --cov=app --cov-report=term-missing -q` -> **79%**.
- Phase 6 backend: setup `pytest` + `pytest-asyncio`; thêm bộ test backend (`test_schemas`, `test_image_validation`, `test_api`, `test_ocr_pipeline`).
- Test backend: `cd backend && .\\venv\\Scripts\\python -m pytest -q` -> **20 passed**.
- Phase 3.8: tích hợp `sonner` toast cho extract/export (success + error), có chống bắn lặp toast theo token state.
- Phase 2.7: `/api/extract` trả `{ data, confidences }`; eval script tính `avg_conf` từ confidence map.

**Session 3**: Phase 2.2 → 2.5 + reorg backend theo MVC + repositories.
- Phase 2.2: RealCardAligner YOLO + perspective warp; pipeline build OK trên CUDA.
- Phase 2.3: RealTextDetector PaddleOCR PP-OCRv5_*_det; switch model qua env `OCR_DETECTOR_MODEL`. Smoke test mobile_det: 4 box / 214ms trên synthetic image.
- Phase 2.4: RealTextRecognizer VietOCR vgg_transformer/vgg_seq2seq + beamsearch toggle. Smoke test seq2seq trên 4 crop English: **4/4 đúng tuyệt đối** (105ms/box trên cuda:0).
- Phase 2.5: RealFieldExtractor rule-based 3-tier (regex + label + fuzzy). 8/8 fields đúng trên fixture sạch + diacritic, **placeholder + confidence=0** cho fields thiếu. **Pipeline FULL REAL sẵn sàng**.
- Reorg: `api/`→`controllers/`, `schemas/`→`models/`, `excel_gen.py`→`excel_service.py`, +`repositories/ModelWeightsRepository`, `models/`→`weights/`.










