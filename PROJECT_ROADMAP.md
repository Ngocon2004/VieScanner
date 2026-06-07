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
| **Phase 2.7** | Tuning với ảnh CCCD thật | ✅ Done (Đã grid-search và chốt bộ tham số tối ưu) |
| **Phase 3*** | UX polish (selective) | ✅ Done (Toast, Skeleton, Confidence, Responsive) |
| **Phase 6*** | Testing (selective) | ✅ Done (Unit/Integration + Playwright E2E hardened) |
| **Sprint DB** | Backend database layer (SQLAlchemy/Alembic/JWT API/history) | ✅ Done |
| **Sprint FE-Int** | Frontend History & Records UI integration | ✅ Done |
| **Documentation** | README final, screenshots | ⏳ In progress (còn 2 screenshot phụ; video/slide đã bỏ scope) |
| **Quality Gate + Batch** | Lọc chất lượng ảnh (cứng/mềm) + xử lý nhiều ảnh + báo lý do ảnh không đạt | ✅ Core done (Session 19) — follow-up: Sprint P |
| **Backlog Tối ưu** | Đề xuất cải tiến accuracy/perf/UX/security (Sprint L–O) | ⏳ Đề xuất (Session 18) |

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
- ✅ Setup `playwright` + `playwright.config.ts` (webServer backend/frontend)
- ✅ `e2e/ocr-export.spec.ts` — scenario upload → OCR → export
- ✅ `e2e/docs-capture.spec.ts` — auto capture screenshots + API call artifact
- ⏳ Harden lệnh `npm run test:e2e`: test đã pass nhưng command còn timeout teardown (cần đổi FE webServer command sang `node .next/standalone/server.js` khi `output: "standalone"`)

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
  - ✅ Upload page (`frontend/docs/screenshots/upload-page.png`)
  - ✅ Form sau OCR (`frontend/docs/screenshots/form-after-ocr.png`)
  - ✅ Sau export (`frontend/docs/screenshots/after-export.png`)
  - ⏳ Excel output mở trong Excel (chưa capture)
  - ⏳ DevTools network tab screenshot (hiện có `frontend/docs/screenshots/api-calls.json`, chưa có ảnh tab)
- ⛔ ~~Demo video 2-3 phút~~ — bỏ scope (sẽ tính sau nếu cần)
- ⛔ ~~Slide thuyết trình 10-15 slides~~ — bỏ scope (sẽ tính sau nếu cần)

**Definition of Done**:
- README đẹp, ai clone về cũng setup được
- Screenshots cơ bản đầy đủ

**Estimate**: 2-3h (không tính làm slide)

---

## 🎁 Optional Sprints (nếu còn thời gian)

### **Sprint I — Dockerize**

- ✅ `backend/Dockerfile` (Python 3.13 slim; default mock OCR cho local/demo)
- ✅ `frontend/Dockerfile` (Next.js standalone build + runtime)
- ✅ `docker-compose.yml` + `docker/nginx/default.conf` — backend + frontend + nginx reverse proxy
- ⏳ README có "Run with Docker" section

**Estimate**: 3-4h

### **Sprint J — Performance**

- ✅ Image resize trước OCR (BE `OCR_MAX_IMAGE_SIDE_PX`; FE preprocess upload)
- ✅ Cache OCR result theo image hash (`OCR_RESULT_CACHE_ENABLED`, TTL)
- ✅ Client-side image compression (Canvas API custom ở `frontend/src/lib/image.ts`)
- ✅ Bundle analyzer FE (`@next/bundle-analyzer`, script `npm run analyze`)

**Estimate**: 3-4h

### **Sprint K — Mặt sau CCCD**

- ⏳ Add mặt sau detector + OCR
- ⏳ Schema: `cccd_back_data` (ngày cấp, nơi cấp, đặc điểm nhân dạng)
- ⏳ UI 2-step upload (mặt trước → mặt sau)

**Estimate**: 4-6h

---

## 🔧 Đề xuất Tối ưu & Cải tiến (Backlog — Session 18)

> Các đề xuất dưới đây được rà soát **trực tiếp từ code** (không chỉ docs). Tất cả đang ở trạng thái ⏳ (chưa làm). Sắp xếp theo nhóm + ROI. Tham chiếu file/dòng để dễ implement sau.

### 🎯 TOP 5 ưu tiên (ROI cao)

1. ⏳ **Đọc QR code mặt trước CCCD** (L1) — accuracy gần như tuyệt đối trên CCCD gắn chip; "ăn điểm" khi present.
2. ⏳ **Semaphore giới hạn OCR đồng thời + warm-up models** (M1, M2) — hết crash khi nhiều request & hết chậm request đầu.
3. ⏳ **AbortController/timeout cho fetch FE** (N1) — `README_TROUBLESHOOTING` nói đã có nhưng code chưa.
4. ⏳ **Batch recognition VietOCR** (L2) — giảm latency stage chậm nhất.
5. ⏳ **Ghi `scans` ở background + retention** (M4, M5) — gọn response & DB không phình.

---

### **Sprint L — Nâng độ chính xác OCR**

**Mục tiêu**: Tăng accuracy end-to-end, đặc biệt với CCCD gắn chip đời mới.

- ⏳ **L1. QR code reader**: CCCD gắn chip (2021+) có QR mã hóa sẵn `số CCCD | CMND cũ | họ tên | ngày sinh | giới tính | địa chỉ | ngày cấp`. Dùng `cv2.QRCodeDetector` (đã có OpenCV) hoặc `pyzbar`; OCR làm fallback khi không có/đọc lỗi QR. Hiện toàn backend **chưa có** xử lý QR/MRZ.
- ⏳ **L2. Batch VietOCR**: `app/services/ocr/stages/recognizer.py` (L143-166) đang `predict()` **từng box** trong vòng lặp → đổi sang `predict_batch()` để giảm latency (10-20 box + beamsearch).
- ⏳ **L3. LLM/VLM fallback extractor**: khi `RealFieldExtractor` để field trống (confidence=0) → gọi LLM/VLM cứu ca khó.
- ⏳ **L4. Mặt sau CCCD** (gộp Sprint K): ngày cấp, nơi cấp, đặc điểm nhận dạng.

**Impact**: L1 rất cao, L2 cao, L3/L4 trung bình | **Effort**: L1/L2 thấp–TB, L3/L4 cao.

---

### **Sprint M — Ổn định & hiệu năng backend**

**Mục tiêu**: Chạy ổn định khi nhiều request + giảm latency cảm nhận.

- ⏳ **M1. Semaphore OCR**: engine là singleton (`lru_cache maxsize=1`), model dùng chung; `asyncio.to_thread` cho chạy song song trên **cùng instance** YOLO/Paddle/VietOCR (không thread-safe) → nguy cơ crash/OOM GPU 4GB. Thêm `asyncio.Semaphore` (env `OCR_MAX_CONCURRENCY`).
- ⏳ **M2. Warm-up lúc startup**: warm engine trong `lifespan` (main.py) khi `OCR_ENGINE=real`; hiện `lifespan` chỉ `ping_database()` (main.py L30-31) → request đầu rất chậm.
- ⏳ **M3. `/health` trả `ocr_engine_ready`** (PHASE_2_PLAN 2.6.3); hiện chỉ trả `status+version` (main.py L68-70).
- ⏳ **M4. Ghi `scans` qua `BackgroundTasks`**: bỏ `await db.commit()` khỏi luồng response (ocr_controller.py L88-104, L208).
- ⏳ **M5. Retention `scans`**: job xóa scan cũ > N ngày — bảng phình mỗi request (kể cả cache hit ghi row `:cache`).
- ⏳ **M6. In-memory LRU trước DB cache**: cache hiện luôn round-trip DB (scan_repository.py L74-96).
- ⏳ **M7. Pool config Postgres** cho prod: `pool_size/max_overflow/pool_recycle` (session.py L16-22 mới chỉ có `pool_pre_ping`).

**Impact**: M1/M2 cao | **Effort**: phần lớn thấp.

---

### **Sprint N — Frontend / UX**

**Mục tiêu**: Không treo UI, duyệt lịch sử/bản ghi mượt hơn.

- ⏳ **N1. AbortController + timeout** cho `request()` trong `frontend/src/lib/api.ts` (L88 `fetch` chưa có `signal`/timeout).
- ⏳ **N2. Nén ảnh trong Web Worker / OffscreenCanvas**: `prepareImageForUpload` chạy Canvas trên main thread → giật UI với ảnh lớn.
- ⏳ **N3. Pagination + search** cho History/Records (BE đã hỗ trợ `limit/offset`, FE mới load 50 dòng).
- ⏳ **N4. SWR/React Query** cache cho History/Records (đỡ fetch lại mỗi lần vào trang).
- ✅ **N5. Commit các file FE chưa track**: `login/register/history/records`, `AuthContext`, `Navbar`, thư mục `e2e/` — đã commit ở Session 20 (khớp "Sprint FE-Int Done").

**Impact**: N1/N3 TB–cao | **Effort**: thấp–TB.

---

### **Sprint O — Bảo mật & vận hành (theo scope đồ án)**

**Mục tiêu**: Sẵn sàng nếu deploy public; bổ sung test.

- ⏳ **O1. Chặn startup nếu `JWT_SECRET=CHANGE_ME`** ở môi trường prod (config.py L63 default yếu).
- ⏳ **O2. Phát hành refresh token thật**: `jwt_refresh_expire_days` có config nhưng `/refresh` chỉ cấp lại access token.
- ⏳ **O3. Rate limiting** (`slowapi`) cho `/extract`, `/auth/*`.
- ⏳ **O4. Composite index** `(image_hash, user_id, status, created_at)` cho query cache (Postgres nhiều dòng).
- ⏳ **O5. Test bổ sung**: token hết hạn/sai, isolation (user A không truy cập dữ liệu user B), biên pagination.
- ⏳ **O6. Harden `npm run test:e2e`** (timeout teardown — Sprint G còn pending).

> **Đính chính khách quan**: CORS `allow_headers=["*"]` + `allow_origins` cụ thể **không phải lỗ hổng**; auth guard client-side bị "bypass" **không lộ dữ liệu** vì BE vẫn chặn bằng `get_current_user` → 2 mục này ưu tiên thấp.

**Impact**: O1/O2 cao nếu deploy | **Effort**: thấp–TB.

---

### **Sprint P — Hoàn thiện Quality Gate + Batch (follow-up Session 19)**

**Bối cảnh**: Core đã xong & verify (backend 37 pass, FE 12 pass, build OK). Các việc dưới đây là phần còn lại để hoàn thiện trọn vẹn — làm tiếp ở phiên sau.

- ⏳ **P1. Cập nhật E2E Playwright cho luồng batch**: `e2e/ocr-export.spec.ts` + `e2e/helpers.ts` đang viết theo luồng 1 ảnh cũ. Cần:
  - `uploadMockImage` → hỗ trợ chọn nhiều file (input giờ có `multiple`).
  - Chờ `BatchResultPanel` (heading "Bước 2: Kết quả phân loại") thay vì form xuất hiện ngay.
  - Chọn 1 ảnh đạt → `CCCDForm` (auto-select ảnh đạt đầu tiên) → export.
  - Rà lại `docs-capture.spec.ts` (screenshot) cho UI mới.
- ⏳ **P2. Chạy thử `OCR_ENGINE=real` + tinh chỉnh ngưỡng `QUALITY_*`** với ảnh CCCD thật (dataset `Data_CCCD_5.26`):
  - Kiểm tra false-positive/negative của `blur_var_hard/soft`, `dark/bright`, `glare`, và card-presence (YOLO).
  - Chốt default phù hợp trong `app/core/config.py` (+ cập nhật `.env.example`, `docs/OCR_PIPELINE.md`).
- ⏳ **P3. Bổ sung test còn thiếu**:
  - BE: quality gate ở real mode / card-presence (hiện mới test OpenCV metrics + batch mock).
  - FE: unit test cho `lib/quality.ts` (precheck) và `useBatchExtract` (gộp client-reject + server-result, race).
- ⏳ **P4. Tài liệu**: thêm mục `POST /api/extract-batch` + bảng tiêu chí chất lượng vào `backend/README.md` & `frontend/README.md` (API contract mới: response `{ data, confidences, quality }`).
- ⏳ **P5. (Liên quan, không bắt buộc)** Sửa lint react-hooks **có sẵn** ở 3 file (đã commit ở Session 20, không thuộc tính năng này): `src/app/AuthContext.tsx` (`set-state-in-effect`), `src/app/history/page.tsx` & `src/app/records/page.tsx` (`accessed before declared` → bọc `useCallback`/khai báo trước effect) + dọn unused vars. Trùng mục N5 (commit các file FE chưa track).

**Definition of Done**: `npm run test:e2e` xanh với luồng batch; ngưỡng `QUALITY_*` chốt theo ảnh thật; test BE/FE bổ sung pass; README mô tả endpoint batch.

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

**Last updated**: Session 20 (commit toàn bộ work tồn đọng + chốt ignore artifact).
- Git: gom toàn bộ thay đổi chưa commit thành **9 commit logic** (conventional commits) theo nhóm tính năng:
  - `chore(repo)`: ignore artifact local (e2e db, tuning json).
  - `feat(backend)` + `test(backend)`: Quality Gate + `/api/extract-batch` + OCR result cache + test.
  - `feat(frontend)` x2: auth + history/records UI; batch upload + tiền kiểm chất lượng + nén ảnh.
  - `chore(frontend)`: standalone output + bundle analyzer + deps e2e.
  - `build(docker)`: dockerize BE + FE + nginx.
  - `test(e2e)`: Playwright suite.
  - `docs`: sync roadmaps/README/troubleshooting + screenshots.
- `.gitignore`: thêm `*.db` (frontend) + mở rộng `scripts/tune_*.json` (backend) → loại `frontend/viescanner-e2e.db` và `backend/scripts/tune_test_run.json` (artifact từ ảnh thật, tránh lộ PII) khỏi git.
- Verify trạng thái đã commit: `git status` sạch; backend `pytest -q` -> **37 passed**; frontend `npm test` -> **12 passed**.
- Chưa push: nhánh `main` đang ahead `origin/main` 9 commit.
- Mục **N5** (commit các file FE chưa track) -> ✅ Done. Lint **P5 vẫn còn**: `npm run lint` báo **3 errors + 2 warnings** ở `AuthContext.tsx`, `history/page.tsx`, `records/page.tsx` (chưa sửa).

**Session 19**: triển khai Quality Gate + Batch xử lý nhiều ảnh.
- Backend: thêm cổng kiểm tra chất lượng ảnh trước OCR (`app/services/image_quality.py`) — độ phân giải, độ nét (Laplacian), độ sáng/lóa, và "có phải thẻ CCCD" (YOLO, real mode). Ngưỡng cứng (chặn) + mềm (cảnh báo) cấu hình qua `QUALITY_*`.
- Backend: endpoint mới `POST /api/extract-batch` (nhiều ảnh) + gắn quality gate vào `/api/extract`; `ImageQualityError` (code `image_quality_low`) trả `details` = danh sách lý do. Schemas: `app/models/quality.py`, `BatchItemResult`/`BatchExtractResponse`.
- Frontend: upload nhiều ảnh, tiền kiểm phía client (`src/lib/quality.ts`), hook `useBatchExtract`, panel kết quả `BatchResultPanel` (đạt/cần xem lại + lý do), `api.ts` thêm `extractBatch` + `fetchWithTimeout` (AbortController — đồng thời xử lý mục N1 của backlog).
- Verify: backend `pytest -q` -> **37 passed** (thêm `test_image_quality`, `test_batch_api`); frontend `npm test` -> **12 passed**; `npm run build` OK; eslint sạch trên các file mới/sửa.
- Lưu ý: e2e Playwright (`ocr-export.spec`) dựa trên luồng 1 ảnh cũ — cần cập nhật cho luồng batch (chưa làm trong session này).
- Lint còn báo lỗi sẵn có ở 3 file CHƯA commit không thuộc tính năng này (`AuthContext.tsx`, `history/page.tsx`, `records/page.tsx`) — đề xuất xử lý riêng.

**Session 18**: rà soát code để bổ sung backlog tối ưu & cải tiến.
- Thêm section "🔧 Đề xuất Tối ưu & Cải tiến (Backlog — Session 18)": Sprint L (accuracy), M (backend ổn định/perf), N (FE/UX), O (bảo mật/vận hành) + TOP 5 ưu tiên.
- Rà soát **trực tiếp code** (không chỉ docs), các điểm đáng lưu ý:
  - `frontend/src/lib/api.ts` `request()` chưa có AbortController/timeout dù `README_TROUBLESHOOTING` nói "đã thêm".
  - `recognizer.py` nhận dạng per-box (chưa dùng `predict_batch`).
  - Toàn backend chưa có đọc QR/MRZ — cơ hội tăng accuracy lớn nhất cho CCCD gắn chip.
  - Chưa có semaphore giới hạn OCR đồng thời; pre-warm chỉ chạy lazy, `lifespan` chỉ ping DB.
  - Các trang FE `login/register/history/records`, `AuthContext`, `Navbar`, thư mục `e2e/` đã có trên disk nhưng **chưa commit git**.
- Không thay đổi code feature; chỉ cập nhật tài liệu roadmap.

**Session 17**: progress sync theo snapshot code/test ngày 2026-05-18.
- Đồng bộ tiến độ roadmap theo thay đổi mới:
  - Sprint I (Dockerize): đã có `backend/Dockerfile`, `frontend/Dockerfile`, `docker-compose.yml`, `docker/nginx/default.conf`.
  - Sprint J (Performance): đã có resize input OCR, cache theo image hash, nén ảnh client-side, bundle analyzer.
  - Sprint G optional: đã có Playwright E2E (`ocr-export`, `docs-capture`) + artifacts screenshot.
  - Sprint H: screenshots tự động đã sinh trong `frontend/docs/screenshots/`; còn ảnh mở file Excel trong app desktop + video + slide.
- Re-verify test suite:
  - `cd backend && .\venv\Scripts\python -m pytest -q` -> **26 passed**.
  - `cd frontend && npm.cmd test -- --run` -> **12 passed**.
  - `cd frontend && npm.cmd run test:e2e` -> 2 test Playwright pass, nhưng command hiện timeout ở bước teardown (cần harden lệnh run).

**Session 16**: progress sync theo snapshot code/test ngày 2026-05-18.
- Trạng thái phase/sprint giữ nguyên so với Session 15:
  - Vẫn pending: Phase 2.7 bước chốt accuracy bằng ground-truth thật.
  - Vẫn pending: Sprint H assets trình bày (screenshots, demo video, slide).
  - Vẫn optional/pending: Playwright E2E và các sprint I/J/K.
- Re-verify test suite:
  - `cd backend && .\venv\Scripts\python -m pytest -q` -> **25 passed**.
  - `cd frontend && npm.cmd test -- --run` -> **12 passed**.
- Không có thay đổi code feature kể từ commit `ac42511`; mục tiêu hiện tại là chốt tuning/report và hoàn thiện tài liệu present.

**Session 15**: sync roadmap sau khi hoàn tất và gom DB layer về `app/db`.
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










