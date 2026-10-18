FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    OCR_ENGINE=mock \
    AUTH_REQUIRED=false

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    libglib2.0-0 \
    libgl1 \
    libsm6 \
    libxext6 \
    libxrender1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . .

EXPOSE 8000

# Áp migration trước khi chạy: thiếu bảng (users/scans/jobs) thì auth, lịch sử và Job API đều lỗi.
CMD ["sh", "-c", "python -m alembic -c app/db/alembic.ini upgrade head && exec python -m uvicorn main:app --host 0.0.0.0 --port 8000"]
