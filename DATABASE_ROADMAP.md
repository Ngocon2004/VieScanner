# VieScanner - Database Roadmap

> Muc tieu: implement tang database cho backend theo huong PostgreSQL/SQLite + SQLAlchemy async + Alembic + JWT.
> Tai lieu thiet ke goc: [setupDatabase.md](./setupDatabase.md)
> Last synced: 2026-05-18 (Session DB-4)
> Ky hieu task: `✅` = da hoan thanh, `⏳` = dang cho hoan thanh.

---

## 1) Current Status

| Block | Noi dung | Status |
|---|---|---|
| DB-Design | Kien truc + schema + implementation plan | ✅ Done |
| DB-Foundation | Config, async engine/session, app lifespan DB ping/dispose | ✅ Done |
| DB-Schema | ORM + Alembic + migration initial | ✅ Done |
| DB-Auth | User model + JWT service + auth APIs | ✅ Done |
| DB-Integration | OCR scan logging + export persistence/corrections | ✅ Done |
| DB-Testing | DB/auth/API tests + regression run | ✅ Done |
| DB-Docs | README/env/context/roadmap sync | ✅ Done |
| DB-Structure | Centralize DB code/migrations under `backend/app/db` | ✅ Done |

---

## 2) Sprint Checklist

### Sprint DB-A - Foundation Setup

- ✅ Add deps vao `backend/requirements.txt` (`sqlalchemy[asyncio]`, `asyncpg`, `alembic`, `passlib[bcrypt]`, `pyjwt`, `email-validator`, `aiosqlite`)
- ✅ Pin `bcrypt==4.0.1` de tranh incompatibility voi passlib tren Python 3.13
- ✅ Update `backend/app/core/config.py` voi `DATABASE_URL`, `DATABASE_ECHO`, `AUTH_REQUIRED`, JWT settings
- ✅ Update `backend/.env.example` voi DB + JWT vars
- ✅ Tao `backend/app/db/base.py` (`DeclarativeBase` + naming convention)
- ✅ Tao `backend/app/db/session.py` (`create_async_engine`, `async_sessionmaker`, `get_db`, `ping_database`, `dispose_engine`)
- ✅ Hook startup ping + shutdown dispose trong `backend/main.py`

Status: ✅ Done

---

### Sprint DB-B - ORM + Migration Initial

- ✅ Tao `backend/app/db/models/` voi `User`, `Scan`, `CCCDRecord`, `Correction`
- ✅ Define constraints/indexes/FK theo spec
- ✅ Setup Alembic (`backend/app/db/alembic.ini`, `backend/app/db/migrations/env.py`, `script.py.mako`)
- ✅ Tao migration `backend/app/db/migrations/versions/0001_initial.py`
- ✅ Sua `alembic.ini` BOM issue de command parse duoc
- ✅ Verify migration cycle:
- ✅ `alembic -c app/db/alembic.ini upgrade head`
- ✅ `alembic -c app/db/alembic.ini downgrade -1`
- ✅ `alembic -c app/db/alembic.ini upgrade head` lai
- ✅ Verify table tao dung: `users`, `scans`, `cccd_records`, `corrections`

Status: ✅ Done

---

### Sprint DB-C - Auth Layer

- ✅ Tao schemas `backend/app/models/auth.py`
- ✅ Tao `backend/app/services/auth_service.py`
- ✅ Tao `backend/app/db/repositories/user_repository.py`
- ✅ Tao `backend/app/dependencies/auth.py` (`get_current_user`, `get_optional_user`, `require_admin`)
- ✅ Tao `backend/app/controllers/auth_controller.py`:
- ✅ `POST /api/auth/register`
- ✅ `POST /api/auth/login`
- ✅ `GET /api/auth/me`
- ✅ `POST /api/auth/refresh`
- ✅ Wire auth router vao `backend/main.py`
- ✅ Giu anonymous mode qua `AUTH_REQUIRED=false`

Status: ✅ Done

---

### Sprint DB-D - OCR/Export Integration

- ✅ Tao repositories DB: `backend/app/db/repositories/scan_repository.py`, `backend/app/db/repositories/cccd_record_repository.py`, `backend/app/db/repositories/correction_repository.py`
- ✅ Update `/api/extract` de ghi `scans` va tra them `scan_id`
- ✅ Update `/api/export` de tao/cap nhat `cccd_records` + set `exported_at`
- ✅ Log corrections tu diff `scan.raw_data` vs final export payload
- ✅ Giu backward compatibility payload export cu va extract response cu

Status: ✅ Done

---

### Sprint DB-E - History/Records APIs

- ✅ Tao `scans_controller.py`:
- ✅ `GET /api/scans`
- ✅ `GET /api/scans/{id}`
- ✅ `DELETE /api/scans/{id}` (admin only)
- ✅ Tao `records_controller.py`:
- ✅ `GET /api/records`
- ✅ `POST /api/records`
- ✅ `PATCH /api/records/{id}`
- ✅ `DELETE /api/records/{id}`
- ✅ Pagination/sort (`created_at desc`) trong repository layer
- ✅ Ownership checks cho scan/record access

Status: ✅ Done

---

### Sprint DB-F - Testing + Verification

- ✅ Them fixture DB in-memory (`sqlite+aiosqlite`) trong `backend/tests/conftest.py`
- ✅ Them `backend/tests/test_auth.py` (register/login/me, duplicate email, wrong password)
- ✅ Them `backend/tests/test_scans_repo.py` (create + list/filter by user)
- ✅ Them `backend/tests/test_records_api.py` (CRUD records)
- ✅ Update test extract de assert field `scan_id`
- ✅ Fix export legacy payload validation de tra `422 validation_error` dung handler
- ✅ Chay full test suite: `26 passed`

Status: ✅ Done

---

### Sprint DB-G - Docs + Handover

- ✅ Update `backend/README.md` section database setup/migrate/rollback
- ✅ Update `backend/.env.example` final DB + JWT vars
- ✅ Update `AI_CONTEXT.md` voi DB layer update note
- ✅ Update `PROJECT_ROADMAP.md` de bo mau thuan "skip PostgreSQL history database"
- ✅ Bo sung runbook ngan ben duoi

Status: ✅ Done

---

### Sprint DB-H - Codebase Consolidation (`app/db`)

- ✅ Move ORM models tu `backend/app/models/orm` -> `backend/app/db/models`
- ✅ Move DB repositories tu `backend/app/repositories/*` -> `backend/app/db/repositories/*`
- ✅ Move Alembic assets tu `backend/migrations` + `backend/alembic.ini` -> `backend/app/db/migrations` + `backend/app/db/alembic.ini`
- ✅ Update `alembic` command path ve `alembic -c app/db/alembic.ini ...`
- ✅ Update toan bo imports trong controllers/services/dependencies/tests/migrations sang `app.db.models` va `app.db.repositories`
- ✅ Duy tri `app/repositories` cho non-DB repository (`ModelWeightsRepository`) de tach boundary ro rang
- ✅ Verify lai migration + tests sau khi move path

Status: ✅ Done

---

## 3) Verification Summary

- `cd backend && .\venv\Scripts\python -m pytest -q` -> **26 passed**
- `cd backend && .\venv\Scripts\alembic -c app/db/alembic.ini upgrade head` -> success
- `cd backend && .\venv\Scripts\alembic -c app/db/alembic.ini downgrade -1` -> success
- `cd backend && .\venv\Scripts\alembic -c app/db/alembic.ini upgrade head` -> success
- Re-verify snapshot 2026-05-18: `cd backend && .\venv\Scripts\python -m pytest -q` -> **26 passed**
- Table check from `viescanner.db`:
- `users`
- `scans`
- `cccd_records`
- `corrections`
- `alembic_version`

---

## 4) Runbook (Quick Ops)

### Setup

```bash
cd backend
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

### Migrate

```bash
venv\Scripts\alembic -c app/db/alembic.ini upgrade head
```

### Verify

```bash
venv\Scripts\python -m pytest -q
```

### Rollback 1 revision

```bash
venv\Scripts\alembic -c app/db/alembic.ini downgrade -1
venv\Scripts\alembic -c app/db/alembic.ini upgrade head
```

---

## 5) Remaining Work (Optional / Next Phase)

- ✅ FE login/history/records UI integration with new backend APIs
- ⏳ Hardening sprint (soft delete, retention policy, audit log)
- ⏳ Bulk export records endpoint
- ⏳ Security hardening cho production deployment

---

## 6) Session Log

### Session DB-4 (2026-05-18) - Progress Sync

- Sync lai so lieu regression test backend sau thay doi OCR cache/logging.
- Re-run regression nhanh backend: `pytest` -> **26 passed**.
- Trang thai cac block DB (DB-Design -> DB-Structure) khong doi, van `✅ Done`.
- Remaining work giu nguyen: hardening + bulk export + FE integration + production security.

### Session DB-3 (2026-05-18) - Progress Sync

- Dong bo lai roadmap DB theo trang thai repository hien tai.
- Xac nhan cac block DB-Design -> DB-Structure van `✅ Done`, khong co thay doi scope.
- Re-run regression nhanh backend: `pytest` van **25 passed**.
- Remaining work giu nguyen: hardening + bulk export + FE integration + production security.



