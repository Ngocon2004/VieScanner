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
- Backend OCR real co the warm-up model o lan dau.

### Cach xu ly
- Frontend da co timeout bang `AbortController` (`fetchWithTimeout` trong
  `src/lib/api.ts`): mac dinh 30s, `/extract` 120s, `/extract-batch` la
  max(120s, 30s x so anh). Het thoi gian cho -> bao loi `timeout` thay vi quay mai.
- Upload lai / bam "Tai len anh khac" / roi trang -> request batch cu bi huy
  phia FE (backend van OCR not batch da nhan vi dang xu ly dong bo).
- Chay qua Docker/nginx: `proxy_read_timeout 600s`, `client_max_body_size 110m`
  (`docker/nginx/default.conf`); neu sua timeout FE thi sua ca nginx.
- Cac request GET (lich su/ban ghi) tu huy khi roi trang (caller `signal` duoc
  gop voi signal timeout) -> khong treo UI, khong set state sau unmount.
- Neu demo nhanh: dung `OCR_ENGINE=mock`.
- Neu can real OCR: bat `OCR_WARMUP_ON_STARTUP=true` (mac dinh) de tai model
  truoc khi nhan request.

## 3) Real OCR rat cham o request dau tien

### Trieu chung
- Lan dau goi OCR real rat lau, lan sau nhanh hon.

### Nguyen nhan
- PaddleOCR/VietOCR tai model lan dau.

### Cach xu ly
- Backend tu warm-up model luc startup khi `OCR_WARMUP_ON_STARTUP=true`
  (mac dinh) -> request dau khong con cham. Kiem tra `GET /health` ->
  `ocr_engine_ready: true` la da san sang.
- Dam bao may co mang o lan chay dau (de tai weights).
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
- OCR result cache dang bat. Cache ap dung cho ca `/extract` va `/extract-batch`,
  tach theo `OCR_ENGINE` va phien ban pipeline (vd `real@1a2b3c4d`): phien ban la hash
  ma nguon `app/services/ocr/` + cac cau hinh `OCR_*` anh huong ket qua, nen sua logic OCR
  hoac doi model/nguong thi ket qua cu tu bi bo qua.
- TTL tinh tu lan OCR that; lan trung cache khong gia han them.
- Trong 1 batch, anh trung nhau (cung hash) chi OCR 1 lan.

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

## 7) Camera khong mo / Job dung o "Dang cho"

- Camera chi chay tren HTTPS hoac `localhost`. Test tren dien thoai qua LAN can
  HTTPS (mkcert/tunnel); khong co camera thi dung tab "Tai file".
- Job khong chay: kiem tra `GET /health` -> `job_queue_size`; DB da migrate chua
  (`alembic -c app/db/alembic.ini upgrade head`, can bang `jobs`, `job_items`).
- Item bao `file_expired`: anh tam bi xoa vi qua `JOB_TTL_MINUTES` truoc khi den luot.

## 8) Checklist xac nhan sau khi sua

1. Chon anh 3-5MB, loading hien ngay (khong dung im).
2. OCR mock tra ket qua trong vai giay.
3. OCR real: request dau co the cham, request sau on dinh hon.
4. Khong con request doi vo han (da co timeout frontend).

## 9) Khi nao can xem log backend

- Treo dai hon 60s.
- OCR that bai lap lai voi cung 1 anh.
- Nghi loi model hoac loi DB.

Khi do, uu tien doc log theo `request_id` de biet request dang dung o buoc nao.

