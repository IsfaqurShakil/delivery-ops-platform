# Base image: Python 3.12 slim (small Linux). We pin 3.12 on purpose.
FROM python:3.12-slim

# Do not write .pyc files, and print logs immediately (better for Docker logs)
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# All next commands run inside /app in the image
WORKDIR /app

# Copy requirements first, so Docker can cache the install step
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy ONLY the folders the app needs (never .env, never .venv)
COPY app ./app
COPY config ./config
COPY alembic ./alembic
COPY alembic.ini .

# Run as a normal user, not root (safer)
RUN useradd --create-home appuser
USER appuser

# Render gives a PORT variable; locally we fall back to 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]