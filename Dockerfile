# bektas-server — personal-site FastAPI backend.
#
# Deployed on the droplet (2026-08-01) after the Vercel deployment started
# returning 500 FUNCTION_INVOCATION_FAILED: its Supabase project had been
# deleted (`ENOTFOUND tenant/user …`), so every request died on connect.
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# psycopg2-binary ships wheels, so no build toolchain is needed.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY changelog.sql ./changelog.sql

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
