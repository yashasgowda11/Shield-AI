# Shield AI Streamlit frontend image.
# Runs as non-root, includes a healthcheck Streamlit can answer.

FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY frontend ./frontend
COPY .streamlit ./.streamlit

RUN useradd --create-home --shell /bin/bash shield && \
    chown -R shield:shield /app
USER shield

EXPOSE 8501

HEALTHCHECK --interval=20s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8501/_stcore/health || exit 1

# --server.address 0.0.0.0       — bind publicly inside the container
# --server.enableCORS/Xsrf=false — safe to disable behind a reverse proxy
CMD ["streamlit", "run", "frontend/app.py", \
     "--server.address", "0.0.0.0", \
     "--server.port", "8501", \
     "--server.headless", "true", \
     "--server.enableCORS", "false", \
     "--server.enableXsrfProtection", "false", \
     "--browser.gatherUsageStats", "false"]
