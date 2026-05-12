# Shield AI — backend image (Cloud Run production)
#
# Differences from local Docker Compose image:
#   - No SQLite default; DATABASE_URL must be set (Cloud SQL PostgreSQL)
#   - No local volume mounts; files go to GCS, vectors to Pinecone
#   - Corpus files bundled into the image (needed for RAG startup)
#   - Reads PORT env var set by Cloud Run (default 8000 for local)
#   - Runs database migrations (alembic upgrade head) on container start
#   - Non-root user for security

FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8000

WORKDIR /app

# System deps: pdfplumber (libxml2), psycopg2 (libpq), curl for healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libxml2 \
        libxslt1.1 \
        libpq-dev \
        curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt

# Application source
COPY backend  ./backend
COPY prompts  ./prompts
COPY scripts  ./scripts
COPY alembic  ./alembic
COPY alembic.ini .

# Corpus is bundled into the image so RAG is ready on cold start
# (no external mount needed — corpus is read-only reference data)
COPY backend/corpus ./backend/corpus

# Log directory (Cloud Run logs go to stdout too, but keep the dir for parity)
RUN mkdir -p /app/logs

# Non-root user
RUN useradd --create-home --shell /bin/bash shield && \
    chown -R shield:shield /app
USER shield

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -fsS http://localhost:${PORT}/health || exit 1

# Run migrations then start the server.
# Cloud Run sets PORT automatically; we pass it to uvicorn.
CMD alembic upgrade head && \
    uvicorn backend.main:app \
        --host 0.0.0.0 \
        --port ${PORT} \
        --workers 1 \
        --log-level info
