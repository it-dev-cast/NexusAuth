# Single container: this repo has no separate frontend build step — the
# SPA is plain static HTML/JS/CSS served by FastAPI itself (see main.py's
# StaticFiles mount and the /ui route), so one image covers both API and UI.
FROM python:3.11-slim

WORKDIR /app

# psycopg-binary/psycopg2-binary and cryptography all ship prebuilt
# manylinux wheels for this base image — no system build toolchain needed.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# upload_dir (app/core/config.py) must exist before app.mount("/uploads", ...)
# runs at import time (main.py) — created here so a fresh container doesn't
# rely on a bind-mounted host directory already existing.
RUN mkdir -p uploads

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
