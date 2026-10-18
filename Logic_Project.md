# VieScanner — Logic Project

## 1. Sơ đồ luồng hệ thống

```text
┌──────────────────── TẦNG 1: ĐẦU VÀO (Frontend) ────────────────────┐
│ A. Quét camera (live scan, tự chụp)                          [Có]   │
│ B. Upload ảnh JPG/PNG/WebP/HEIC (1..n ảnh)                   [Có]   │
│ C. Import PDF (mỗi trang 1 ảnh) · ZIP: bỏ khỏi phạm vi       [Có]   │
│                            ▼                                        │
│  Tiền xử lý client: decode → xoay EXIF → resize/nén (Web Worker)    │
│  → tiền kiểm chất lượng (lib/quality.ts)                     [Có]   │
└────────────────────────────┬───────────────────────────────────────┘
                             ▼  POST /api/jobs (multipart, n file)
┌──────────────────── TẦNG 2: TIẾP NHẬN (Backend) ───────────────────┐
│ Validate file → HEIC→JPEG, PDF→ảnh từng trang → tạo Job + Items     │
│ → hàng đợi xử lý (semaphore) → trả job_id ngay               [Có]   │
│ Theo dõi: GET /api/jobs/{id} · hủy · khôi phục khi restart   [Có]   │
└────────────────────────────┬───────────────────────────────────────┘
                             ▼  (mỗi ảnh)
┌──────────────────── TẦNG 3: XỬ LÝ ẢNH (ML/DL) ─────────────────────┐
│ ① Quality gate            (OpenCV + YOLO)                    [Có]   │
│ ② Phân loại mặt/loại thẻ  (Rule → CNN classifier)            [Mới]  │
│ ③ Căn thẻ                 (YOLO 4 góc + warp)                [Sửa]  │
│ ④ Đọc mã máy: mặt trước → QR [Có] · mặt sau → MRZ            [Mới]  │
│ ⑤ Làm sạch ảnh            (OpenCV)                           [Có]   │
│ ⑥ Phát hiện chữ           (PaddleOCR DBNet)                  [Có]   │
│ ⑦ Nhận dạng chữ           (VietOCR batch)                    [Có]   │
│ ⑧ Trích trường theo layout: front / back / loại thẻ          [Sửa]  │
└────────────────────────────┬───────────────────────────────────────┘
                             ▼
┌──────────────────── TẦNG 4: GHÉP & HỢP NHẤT ───────────────────────┐
│ Ghép mặt trước↔sau thành 1 hồ sơ (số CCCD / MRZ / tên file / thứ tự)│
│ Fusion theo trường: QR > MRZ(checksum) > OCR                        │
│ Kiểm tra chéo + quy tắc nghiệp vụ → confidence cuối                 │
└────────────────────────────┬───────────────────────────────────────┘
                             ▼
┌──────────────────── TẦNG 5: KẾT QUẢ ───────────────────────────────┐
│ Hồ sơ/người: dữ liệu + confidence + nguồn + cảnh báo                │
│ UI review (sửa trường thấp, ghép tay) → lưu records + corrections   │
│ → Xuất Excel nhiều dòng / CSV / JSON                                │
└────────────────────────────┬───────────────────────────────────────┘
                             ▼
┌──────────────────── TẦNG 6: DATABASE & HỌC LẠI ────────────────────┐
│ users · jobs · job_items · scans · scan_pairs · cccd_records        │
│ corrections · exports · refresh_tokens                              │
│ corrections → dữ liệu huấn luyện → fine-tune → quay lại Tầng 3      │
└────────────────────────────────────────────────────────────────────┘
```

## 2. Sơ đồ các giai đoạn dự án

```text
┌──────────────────── GIAI ĐOẠN 1: NỀN TẢNG ─────────────────────────┐
│ Phase 0    Quick wins (favicon, gitignore, lint)             [Xong] │
│ Phase 1 BE Logging, exception handler, validator, DI         [Xong] │
│ Phase 1 FE Strict TS, zod, hooks, error/loading              [Xong] │
└────────────────────────────┬───────────────────────────────────────┘
                             ▼
┌──────────────────── GIAI ĐOẠN 2: OCR MẶT TRƯỚC ────────────────────┐
│ 2.0 Scaffolding (interface + mock + pipeline)                [Xong] │
│ 2.1 Cleaner · 2.2 Aligner · 2.3 Detector                     [Xong] │
│ 2.4 Recognizer · 2.5 Extractor · 2.7 Tuning ảnh thật         [Xong] │
└────────────────────────────┬───────────────────────────────────────┘
                             ▼
┌──────────────────── GIAI ĐOẠN 3: SẢN PHẨM HOÀN CHỈNH ──────────────┐
│ Phase 3  UX polish (toast, skeleton, confidence, mobile)     [Xong] │
│ Phase 6  Testing (pytest, vitest, Playwright E2E)            [Xong] │
│ Sprint DB  SQLAlchemy + Alembic + JWT + lịch sử              [Xong] │
│ Sprint FE-Int  Trang History / Records / Login               [Xong] │
│ Docker · Performance (resize, cache, nén client)             [Xong] │
└────────────────────────────┬───────────────────────────────────────┘
                             ▼
┌──────────────────── GIAI ĐOẠN 4: TỐI ƯU (S19 → S24) ───────────────┐
│ Quality gate + batch nhiều ảnh                               [Xong] │
│ QR mặt trước · semaphore + warm-up · VietOCR batch           [Xong] │
│ Hủy request FE · ghi scan nền + retention · E2E batch        [Xong] │
│ Tài liệu (README, ARCHITECTURE, OCR_PIPELINE)            [Gần xong] │
└────────────────────────────┬───────────────────────────────────────┘
                             ▼
┌──────────────────── GIAI ĐOẠN 5: HAI MẶT CCCD (kế hoạch) ──────────┐
│ S0  Dọn nền: commit/push, che PII trong log                         │
│ S1  Database: jobs, scan_pairs, trường mặt sau, xuất nhiều dòng     │
│ S2  Mặt sau: phân loại mặt (rule) + BackExtractor                   │
│ S3  MRZ + fusion + kiểm tra chéo                                    │
│ S4  Job API + import ZIP/PDF/HEIC + ghép cặp                        │
│ S5  Giao diện review + ghép tay + xuất file                         │
└────────────────────────────┬───────────────────────────────────────┘
                             ▼
┌──────────────────── GIAI ĐOẠN 6: MỞ RỘNG & HOÀN THIỆN ─────────────┐
│ S6  Quét camera        S7  Tìm kiếm/phân trang/SWR                  │
│ S8  Bảo mật + vận hành (refresh token, rate limit, pool, Docker)    │
│ S9  Train CNN classifier, fine-tune YOLO mặt sau, fast mode         │
│ S10 Gán nhãn tay, đánh giá, tài liệu cuối                           │
│ S11 (tùy chọn) LLM fallback, thẻ Căn cước 2024                      │
└────────────────────────────────────────────────────────────────────┘
```
