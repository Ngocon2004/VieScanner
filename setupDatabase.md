# Setup Database — VieScanner

> Tài liệu thiết kế & hướng dẫn triển khai tầng database cho VieScanner backend.
> Trạng thái: **Đề xuất / chưa implement**. File này gói toàn bộ phân tích để review trước khi code.

---

## 1. Tổng quan

VieScanner hiện tại **stateless** — flow `upload → OCR → user edit → export Excel` không lưu lại gì. Mục tiêu của tầng database mới:

- Lưu **lịch sử OCR** (mỗi lần quét → 1 row, kèm raw output + confidence + thời gian).
- Lưu **bản ghi CCCD final** sau khi user review & export.
- Lưu **corrections** (trường nào OCR sai, user sửa thành gì) → phục vụ tuning model về sau.
- Có **users + JWT auth** sẵn để mở rộng multi-user, nhưng **vẫn cho phép anonymous** để demo cũ chạy được.

Phạm vi: **chỉ backend**. Frontend chưa đụng tới trong phase này.

---

## 2. Quyết định kiến trúc

| Khía cạnh | Lựa chọn | Lý do |
|---|---|---|
| DB engine | **PostgreSQL** | Production-grade, hỗ trợ JSONB cho `raw_data` / `confidences`, ENUM, UUID native. |
| Hosting | **Supabase hoặc Neon (free tier)** | Không cần install Postgres local. Connection string trong `.env`. Free tier đủ cho đồ án. |
| Driver | **asyncpg** | Async-native, hiệu năng tốt nhất với SQLAlchemy 2.0. |
| ORM | **SQLAlchemy 2.0 (async)** | Chuẩn công nghiệp, hỗ trợ async, generate Alembic migration tốt. |
| Migration | **Alembic** | Versioned schema migration, autogenerate từ model. |
| Auth | **JWT (PyJWT) + bcrypt (passlib)** | Stateless, mở rộng dễ. Có thể tắt qua env `AUTH_REQUIRED=false`. |
| Password hash | **bcrypt** (passlib) | Chuẩn thực tế cho password storage. |
| Lưu ảnh CCCD | **KHÔNG** | Tránh PII, DB nhẹ. Chỉ lưu `image_hash` (sha256) để dedup nếu cần. |

---

## 3. Schema design

### 3.1 Bảng `users`

```text
users
├── id              UUID PK             (default gen_random_uuid)
├── email           VARCHAR UNIQUE NOT NULL
├── password_hash   VARCHAR NOT NULL    -- bcrypt
├── full_name       VARCHAR
├── role            ENUM('admin','user')  default 'user'
├── is_active       BOOL default true
├── created_at      TIMESTAMPTZ default now()
└── updated_at      TIMESTAMPTZ default now()
```

Index: `email` (unique đã tạo index).

### 3.2 Bảng `scans` — lịch sử mỗi lần OCR

```text
scans
├── id              UUID PK
├── user_id         UUID FK users (nullable: anonymous)
├── request_id      UUID                -- khớp với X-Request-ID middleware log
├── filename        VARCHAR
├── mime_type       VARCHAR
├── size_bytes      BIGINT
├── image_hash      VARCHAR(64)         -- sha256 hex
├── ocr_engine      VARCHAR             -- mock | real | hybrid
├── status          ENUM('success','failed','partial')
├── raw_data        JSONB               -- CCCDData OCR trả về (chưa user-edit)
├── confidences     JSONB               -- {field_name: float}
├── error_code      VARCHAR (nullable)
├── error_message   TEXT (nullable)
├── duration_ms     INT
└── created_at      TIMESTAMPTZ default now()
```

Index: `user_id`, `image_hash`, `created_at desc`.

### 3.3 Bảng `cccd_records` — bản ghi CCCD final sau khi user review

```text
cccd_records
├── id              UUID PK
├── scan_id         UUID FK scans (nullable)
├── user_id         UUID FK users (nullable)
├── id_number       VARCHAR(12)         -- KHÔNG unique vì có thể re-scan / sửa
├── full_name       VARCHAR
├── dob             DATE
├── gender          VARCHAR(3)          -- 'Nam' | 'Nữ'
├── nationality     VARCHAR
├── origin          TEXT
├── residence       TEXT
├── expiry_date     DATE (nullable)
├── exported_at     TIMESTAMPTZ (nullable) -- set khi user click Export Excel
├── created_at      TIMESTAMPTZ default now()
└── updated_at      TIMESTAMPTZ default now()
```

Index: `id_number`, `user_id`, `scan_id`.

### 3.4 Bảng `corrections` — log trường user sửa

```text
corrections
├── id                  UUID PK
├── scan_id             UUID FK scans
├── field_name          VARCHAR             -- id_number | full_name | dob | ...
├── ocr_value           TEXT
├── corrected_value     TEXT
├── confidence_at_ocr   FLOAT
└── created_at          TIMESTAMPTZ default now()
```

Index: `scan_id`, `field_name`.

### 3.5 ER Diagram (text)

```
                      ┌──────────┐
                      │  users   │
                      └────┬─────┘
                           │ 1
                  ┌────────┼────────┐
                  │ N      │ N      │
            ┌─────▼──┐ ┌───▼──────────┐
            │ scans  │ │ cccd_records │
            └────┬───┘ └──────┬───────┘
                 │ 1          │
                 │ N          │
         ┌───────▼──────┐     │
         │ corrections  │     │
         └──────────────┘     │
                              │
            scans.id ◄────────┘ (cccd_records.scan_id, nullable)
```

- 1 user → N scans, N records
- 1 scan → N corrections, có thể có 0..1 record
- record có thể tồn tại không qua scan (user nhập thủ công)

---

## 4. Implementation Plan (13 bước)

### 4.1 Dependencies — thêm vào `backend/requirements.txt`

```text
sqlalchemy[asyncio]==2.0.36
asyncpg==0.30.0
alembic==1.14.0
passlib[bcrypt]==1.7.4
pyjwt==2.10.1
email-validator==2.2.0
```

### 4.2 Config — update `backend/app/core/config.py` & `.env.example`

Thêm các settings:

```python
# Database
database_url: str = "postgresql+asyncpg://user:pass@host:5432/dbname"
database_echo: bool = False

# Auth / JWT
auth_required: bool = False        # false = cho phép anonymous, demo cũ chạy
jwt_secret: str = "CHANGE_ME"
jwt_algorithm: str = "HS256"
jwt_access_expire_min: int = 60
jwt_refresh_expire_days: int = 7
```

### 4.3 Database layer — folder mới `backend/app/db/`

- `db/base.py` — `class Base(DeclarativeBase)` + naming conventions cho FK/unique/index (giúp Alembic tên ổn định).
- `db/session.py` — tạo `engine = create_async_engine(...)`, `async_session_maker`, FastAPI dependency `get_db()` yield AsyncSession.
- `db/__init__.py` — re-export.

### 4.4 ORM models — folder mới `backend/app/models/orm/`

Tách riêng với Pydantic schemas hiện có, **không động vào `models/cccd.py`**:

- `orm/__init__.py` — import all để Alembic autogenerate thấy.
- `orm/user.py` → `User`
- `orm/scan.py` → `Scan`
- `orm/cccd_record.py` → `CCCDRecord`
- `orm/correction.py` → `Correction`

### 4.5 Pydantic schemas mới — cùng `backend/app/models/`

- `auth.py` — `UserCreate`, `UserRead`, `UserLogin`, `Token`, `TokenPayload`.
- `scan.py` — `ScanRead`, `ScanListItem`.
- `record.py` — `CCCDRecordCreate`, `CCCDRecordRead`, `CCCDRecordUpdate`.
- Giữ nguyên `cccd.py` hiện tại — không phá API cũ.

### 4.6 Repositories — mở rộng `backend/app/repositories/`

- `user_repository.py` — CRUD user, `get_by_email`.
- `scan_repository.py` — `create_scan`, `list_by_user`, `get_by_id`, `find_by_image_hash`.
- `cccd_record_repository.py` — CRUD record + `mark_exported`.
- `correction_repository.py` — `bulk_insert(corrections)`.

### 4.7 Services — mở rộng `backend/app/services/`

- `auth_service.py` — `hash_password`, `verify_password`, `create_access_token`, `decode_token`, `register_user`, `authenticate`.
- Update `ocr_engine.py`: sau `extract()` → ghi 1 row vào `scans` (kèm status, raw_data, confidences, duration_ms). Trả thêm `scan_id` ra response.
- Update `excel_service.py` (hoặc controller): khi export thành công → set `cccd_records.exported_at = now()`.

### 4.8 Auth dependencies — folder mới `backend/app/dependencies/`

- `auth.py` — `get_current_user(token)` (bắt buộc auth), `get_optional_user` (cho endpoint anonymous-friendly), `require_admin`.

### 4.9 Controllers

**Mới**:
- `auth_controller.py`
  - `POST /api/auth/register`
  - `POST /api/auth/login`
  - `GET /api/auth/me`
  - `POST /api/auth/refresh`
- `scans_controller.py`
  - `GET /api/scans` (list history của user)
  - `GET /api/scans/{id}` (chi tiết scan)
  - `DELETE /api/scans/{id}` (admin only)
- `records_controller.py`
  - `GET /api/records`
  - `POST /api/records`
  - `PATCH /api/records/{id}`
  - `DELETE /api/records/{id}`

**Update** (giữ tương thích payload):
- `ocr_controller.py` — inject session, ghi scan vào DB; trả response thêm `scan_id` (FE cũ ignore field thừa, không break).
- `export_controller.py` — accept optional `record_id` trong body, save record nếu chưa có, set `exported_at`.

### 4.10 Alembic

- `backend/app/db/alembic.ini`
- `backend/app/db/migrations/env.py` — config sync engine cho migration (chuyển `postgresql+asyncpg://` → `postgresql+psycopg2://` cho alembic chạy).
- `backend/app/db/migrations/script.py.mako`
- `backend/app/db/migrations/versions/0001_initial.py` (autogenerate từ ORM models).

### 4.11 Lifespan update — `backend/main.py`

- Trong `lifespan`: ping DB (`SELECT 1`) ở startup → fail-fast nếu connection sai.
- Dispose engine ở shutdown.
- Include 3 router mới với prefix `/api`.

### 4.12 Tests — `backend/tests/`

- `test_auth.py` — register / login / me happy path + duplicate email + sai password.
- `test_scans_repo.py` — create + list + filter by user.
- `test_records_api.py` — CRUD records (auth required).
- DB test: dùng `sqlite+aiosqlite` in-memory (nhanh, không cần Postgres real). Override `DATABASE_URL` qua fixture.

### 4.13 Documentation

- Update `backend/README.md`: thêm section "Database setup" (Supabase/Neon connection string, `alembic upgrade head`).
- Update `backend/.env.example`: thêm tất cả var DB + JWT.
- Update `AI_CONTEXT.md`: tree thư mục mới + tầng DB.
- Update `PROJECT_ROADMAP.md`: PostgreSQL không còn mark SKIP, thêm "Sprint DB" mới.

---

## 5. Files to Create / Modify

### Create

```
backend/app/db/
├── __init__.py
├── base.py
└── session.py

backend/app/models/orm/
├── __init__.py
├── user.py
├── scan.py
├── cccd_record.py
└── correction.py

backend/app/models/
├── auth.py
├── scan.py
└── record.py

backend/app/repositories/
├── user_repository.py
├── scan_repository.py
├── cccd_record_repository.py
└── correction_repository.py

backend/app/services/
└── auth_service.py

backend/app/dependencies/
├── __init__.py
└── auth.py

backend/app/controllers/
├── auth_controller.py
├── scans_controller.py
└── records_controller.py

backend/
└── app/db/
    ├── alembic.ini
    └── migrations/
    ├── env.py
    ├── script.py.mako
    └── versions/0001_initial.py

backend/tests/
├── test_auth.py
├── test_scans_repo.py
└── test_records_api.py
```

### Modify

```
backend/requirements.txt
backend/app/core/config.py
backend/.env.example
backend/main.py
backend/app/controllers/ocr_controller.py
backend/app/controllers/export_controller.py
backend/app/services/ocr_engine.py
backend/README.md
AI_CONTEXT.md
PROJECT_ROADMAP.md
```

---

## 6. Setup Steps (cách chạy thực tế)

### Bước 1 — Tạo PostgreSQL trên cloud

**Phương án A: Supabase**

1. Truy cập https://supabase.com → Sign up → New project.
2. Region: chọn Singapore (gần VN).
3. Đặt password DB → lưu lại.
4. Vào **Project Settings → Database → Connection string → URI** → copy.

Connection string mẫu:
```
postgresql://postgres.<project-ref>:<password>@aws-0-ap-southeast-1.pooler.supabase.com:6543/postgres
```

Convert sang async driver (đổi prefix):
```
postgresql+asyncpg://postgres.<project-ref>:<password>@aws-0-ap-southeast-1.pooler.supabase.com:6543/postgres
```

**Phương án B: Neon**

1. Truy cập https://neon.tech → New project → region Singapore.
2. Copy connection string từ dashboard.
3. Convert prefix `postgresql://` → `postgresql+asyncpg://`.

### Bước 2 — Cấu hình `.env`

```bash
cd backend
cp .env.example .env
```

Mở `backend/.env` thêm:

```env
# Database
DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/dbname
DATABASE_ECHO=false

# Auth
AUTH_REQUIRED=false
JWT_SECRET=<generate bằng `python -c "import secrets; print(secrets.token_urlsafe(32))"`>
JWT_ALGORITHM=HS256
JWT_ACCESS_EXPIRE_MIN=60
JWT_REFRESH_EXPIRE_DAYS=7
```

### Bước 3 — Cài dependencies

```bash
cd backend
venv\Scripts\activate
pip install -r requirements.txt
```

### Bước 4 — Chạy migration

Khởi tạo Alembic (chỉ làm 1 lần đầu):
```bash
alembic -c app/db/alembic.ini upgrade head
```

Khi sau này đổi schema:
```bash
alembic -c app/db/alembic.ini revision --autogenerate -m "add some field"
alembic -c app/db/alembic.ini upgrade head
```

### Bước 5 — Verify

Khởi động server:
```bash
uvicorn main:app --reload
```

Test endpoints:
```bash
# Health (vẫn có sẵn)
curl http://localhost:8000/health

# Register user
curl -X POST http://localhost:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"test@example.com\",\"password\":\"secret123\",\"full_name\":\"Test\"}"

# Login → lấy access_token
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"test@example.com\",\"password\":\"secret123\"}"

# Extract (anonymous, AUTH_REQUIRED=false)
curl -X POST http://localhost:8000/api/extract \
  -F "file=@cccd_sample.jpg"
# → response có thêm field "scan_id"

# List scans (cần token)
curl http://localhost:8000/api/scans \
  -H "Authorization: Bearer <access_token>"
```

Trên Supabase / Neon dashboard, vào **Table Editor** → kiểm tra 4 bảng đã được tạo: `users`, `scans`, `cccd_records`, `corrections`.

---

## 7. Verification Checklist

- [ ] `pip install -r requirements.txt` thành công, không conflict.
- [ ] `alembic -c app/db/alembic.ini upgrade head` tạo đủ 4 bảng trên Supabase/Neon.
- [ ] `pytest -q` pass toàn bộ test cũ + test mới.
- [ ] `POST /api/auth/register` + `/api/auth/login` → trả JWT hợp lệ.
- [ ] `POST /api/extract` (không auth) → response có `scan_id`, DB có row trong `scans` với `user_id=NULL`.
- [ ] `POST /api/extract` (có Bearer token) → DB có row với `user_id=<uuid>`.
- [ ] `POST /api/export` → DB có row trong `cccd_records` với `exported_at` set.
- [ ] `GET /api/scans` → list history của user hiện tại, sort theo `created_at desc`.
- [ ] Frontend cũ (`npm run dev`) vẫn upload + extract + export bình thường (response thừa `scan_id` được ignore).
- [ ] OpenAPI docs (`/docs`) hiển thị đầy đủ endpoint mới.

---

## 8. Risks / Considerations

| Vấn đề | Mức | Cách xử lý |
|---|---|---|
| FE cũ không có UI login → bị 401 nếu bật auth | 🟡 | Default `AUTH_REQUIRED=false`. Anonymous scan ghi với `user_id=NULL`. Khi nào FE có login form thì bật. |
| CCCD là PII nhạy cảm | 🔴 | KHÔNG lưu ảnh. README cảnh báo demo này không deploy public với CCCD thật. Có thể thêm cron job xoá scan cũ > N ngày. |
| Supabase / Neon free tier giới hạn | 🟢 | Neon free 0.5GB, Supabase free 500MB → đủ cho đồ án. Project pause sau 1 tuần inactive (Supabase) → reactivate khi dùng lại. |
| Alembic + async URL | 🟡 | `app/db/migrations/env.py` cần convert `postgresql+asyncpg://` → `postgresql+psycopg2://` (cài thêm `psycopg2-binary` cho alembic chạy sync) HOẶC dùng async migration mode của Alembic. Sẽ chọn cách đơn giản nhất khi implement. |
| Test DB | 🟢 | Dùng `sqlite+aiosqlite` in-memory, override qua fixture. Không cần Postgres khi chạy `pytest`. Lưu ý: SQLite không có JSONB native nhưng SQLAlchemy 2.0 dùng `JSON` type abstract → vẫn hoạt động cho test. |
| Bcrypt trên Windows + Python 3.13 | 🟡 | `passlib[bcrypt]` đôi khi warning version detection trên 3.13 — không ảnh hưởng chức năng. Có thể chuyển sang `bcrypt` raw nếu cần. |
| Connection pooling khi serverless | 🟢 | Supabase có connection pooler (port 6543) — dùng URL pooler thay vì direct (5432) để tránh exhaust connections. |
| Latency Supabase/Neon | 🟢 | ~50-100ms từ VN, có thể chậm hơn local. Chấp nhận được cho dev/demo. |

---

## 9. Roadmap / Next Steps (sau khi DB xong)

### Phase tiếp theo (FE work — chưa nằm trong scope file này)

- [ ] FE: thêm trang `/login` + `/register` (nếu bật `AUTH_REQUIRED=true`).
- [ ] FE: thêm trang `/history` list scans, click vào → re-fill form từ raw_data.
- [ ] FE: thêm trang `/records` quản lý CCCD records, search theo `id_number` / `full_name`.
- [ ] FE: track corrections — khi user sửa field, gửi diff về backend khi submit.

### Tính năng nâng cao (optional)

- [ ] Soft delete (cột `deleted_at`) thay vì hard delete.
- [ ] Audit log table (ai làm gì, khi nào).
- [ ] Export tất cả records ra 1 file Excel hàng loạt (`POST /api/records/export-bulk`).
- [ ] Statistics endpoint: accuracy theo thời gian, top fields hay sai.
- [ ] Webhook khi scan thành công.
- [ ] Rate limit per user (nếu deploy public).

---

## 10. Tham khảo

- [SQLAlchemy 2.0 Async docs](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html)
- [Alembic docs](https://alembic.sqlalchemy.org/en/latest/)
- [PyJWT docs](https://pyjwt.readthedocs.io/en/stable/)
- [FastAPI Security tutorial](https://fastapi.tiangolo.com/tutorial/security/)
- [Supabase Postgres docs](https://supabase.com/docs/guides/database/overview)
- [Neon docs](https://neon.tech/docs/introduction)

---

**Last updated**: Session khi user yêu cầu thêm tầng database (đề xuất, chưa implement).
