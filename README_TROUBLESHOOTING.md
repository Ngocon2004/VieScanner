# VieScanner Troubleshooting (No-Hang Checklist)

Tai lieu nay gom cac loi "treo/cham/khong phan hoi" thuong gap va cach xu ly dut diem.

## 1) UI co cam giac treo ngay sau khi chon anh

### Trieu chung
- Chon anh xong, UI dung im mot luc moi hien "Dang xu ly...".

### Nguyen nhan
- Frontend preprocess anh (decode/resize/compress) truoc khi bat trang thai loading.

### Cach xu ly
- Bat loading ngay khi bat dau `readFile`.
- Neu can, giam muc nen anh:
  - `NEXT_PUBLIC_MAX_UPLOAD_SIDE_PX=1600`
  - `NEXT_PUBLIC_MIN_COMPRESS_BYTES=307200`
  - `NEXT_PUBLIC_UPLOAD_JPEG_QUALITY=0.85`

## 2) Request `/extract` doi rat lau

### Trieu chung
- Nut dang xu ly quay mai, khong thay loi.

### Nguyen nhan
- Frontend `fetch` chua co timeout.
- Backend OCR real co the warm-up model o lan dau.

### Cach xu ly
- Them timeout bang `AbortController` (VD 30-60s) cho `/extract`.
- Neu demo nhanh: dung `OCR_ENGINE=mock`.
- Neu can real OCR: chay warm-up truoc de tai model xong roi moi test UI.

## 3) Real OCR rat cham o request dau tien

### Trieu chung
- Lan dau goi OCR real rat lau, lan sau nhanh hon.

### Nguyen nhan
- PaddleOCR/VietOCR tai model lan dau.

### Cach xu ly
- Khoi dong backend truoc, goi 1 request warm-up.
- Dam bao may co mang o lan chay dau.
- Neu khong can real OCR, giu `OCR_ENGINE=mock`.

## 4) OCR out-of-memory hoac latency cao voi anh lon

### Trieu chung
- Backend chay cham bat thuong voi anh kich thuoc lon.

### Nguyen nhan
- Anh input qua lon lam detector/recognizer ton RAM/CPU.

### Cach xu ly
- Giu:
  - `OCR_MAX_IMAGE_SIDE_PX=2000` (hoac 1600 neu may yeu)
- Dong bo voi frontend resize de tranh xu ly qua nang o backend.

## 5) Cache ket qua OCR gay nham khi debug

### Trieu chung
- Upload lai anh cu ma ket qua tra ve "nhanh bat thuong", nghi ngo da dung cache.

### Nguyen nhan
- OCR result cache dang bat.

### Cach xu ly
- Tat cache khi debug:
  - `OCR_RESULT_CACHE_ENABLED=false`
- Hoac giam TTL:
  - `OCR_RESULT_CACHE_TTL_SECONDS=60`

## 6) Quick config de chay on dinh (local dev)

### backend/.env
```env
OCR_ENGINE=mock
OCR_MAX_IMAGE_SIDE_PX=2000
OCR_RESULT_CACHE_ENABLED=true
OCR_RESULT_CACHE_TTL_SECONDS=86400
```

### frontend/.env.local
```env
NEXT_PUBLIC_API_URL=http://localhost:8000/api
NEXT_PUBLIC_MAX_UPLOAD_SIDE_PX=2000
NEXT_PUBLIC_MIN_COMPRESS_BYTES=614400
NEXT_PUBLIC_UPLOAD_JPEG_QUALITY=0.9
```

## 7) Checklist xac nhan sau khi sua

1. Chon anh 3-5MB, loading hien ngay (khong dung im).
2. OCR mock tra ket qua trong vai giay.
3. OCR real: request dau co the cham, request sau on dinh hon.
4. Khong con request doi vo han (da co timeout frontend).

## 8) Khi nao can xem log backend

- Treo dai hon 60s.
- OCR that bai lap lai voi cung 1 anh.
- Nghi loi model hoac loi DB.

Khi do, uu tien doc log theo `request_id` de biet request dang dung o buoc nao.

