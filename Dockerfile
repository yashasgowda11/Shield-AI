# Shield AI backend image.
# Python 3.11 slim. Installs deps, copies source, runs as non-root.

FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# System deps for pdfplumber, numpy, faiss, plus curl for the healthcheck.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libxml2 \
        libxslt1.1 \
        curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY backend ./backend
COPY prompts ./prompts
COPY scripts ./scripts

# Persistent dirs — volume-mounted at runtime.
RUN mkdir -p /data /app/backend/rag/cache /app/backend/uploads /app/logs

ENV DATABASE_URL=sqlite:////data/shield.db

# Non-root user
RUN useradd --create-home --shell /bin/bash shield && \
    chown -R shield:shield /app /data
USER shield

EXPOSE 8000

HEALTHCHECK --interval=20s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
