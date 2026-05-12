# Shield AI — Streamlit frontend image (Cloud Run production)
#
# BACKEND_URL must be set to the Cloud Run backend service URL at deploy time.
# Cloud Run sets PORT automatically (default 8501 for local).

FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8501

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY frontend   ./frontend
COPY .streamlit ./.streamlit

# Non-root user
RUN useradd --create-home --shell /bin/bash shield && \
    chown -R shield:shield /app
USER shield

EXPOSE 8501

HEALTHCHECK --interval=20s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -fsS http://localhost:${PORT}/_stcore/health || exit 1

CMD streamlit run frontend/app.py \
    --server.address 0.0.0.0 \
    --server.port ${PORT} \
    --server.headless true \
    --server.enableCORS false \
    --server.enableXsrfProtection false \
    --browser.gatherUsageStats false
