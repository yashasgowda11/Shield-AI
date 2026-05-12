"""FastAPI app entry point.

Run with: uvicorn backend.main:app --reload --port 8000
Docs at: http://localhost:8000/docs

Set SKIP_RAG_INIT=true in .env to skip embedding the corpus on boot
(useful during fast iteration when you don't need RAG features).

Logging
-------
Daily rotating log files are written to logs/shield.log (rolled at midnight UTC).
Override behaviour with env vars:
  SHIELD_LOG_DIR           — directory for log files  (default: logs/)
  SHIELD_LOG_LEVEL         — root log level           (default: INFO)
  SHIELD_LOG_RETENTION_DAYS— days of log files to keep (default: 30)
"""

# setup_logging() MUST be the very first call — before any other import that
# touches logging so every subsequent getLogger() inherits the configuration.
from backend.logging_config import setup_logging
setup_logging()

import logging
import os
import time
import traceback
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.api import audit_logs, contracts, dashboard, graph, query, rag
from backend.db import init_db

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lifespan — startup / shutdown
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    # ---- Startup ----
    logger.info("Shield AI starting up")
    init_db()

    if os.getenv("SKIP_RAG_INIT", "false").lower() != "true":
        try:
            from backend.rag.ingest import build_all_indices
            counts = build_all_indices()
            logger.info("RAG ready: %s", counts)
        except Exception:
            # Don't crash the backend if RAG init fails — log and continue
            # so other endpoints (upload, contract list, etc.) still work.
            logger.exception("RAG initialization failed; continuing without RAG")
    else:
        logger.info("SKIP_RAG_INIT=true — skipping RAG ingestion")

    logger.info("Shield AI startup complete")
    yield

    # ---- Shutdown ----
    logger.info("Shield AI shutting down")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Shield AI",
    description="AI Governance Platform for Enterprise Contract Risk Assessment",
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Request / response logging middleware
# ---------------------------------------------------------------------------

@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log every HTTP request with method, path, status code, and elapsed time."""
    start = time.perf_counter()
    response = None
    try:
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.info(
            "HTTP %s %s → %d  (%.1f ms)",
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
        )
        return response
    except Exception as exc:
        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.error(
            "HTTP %s %s → UNHANDLED EXCEPTION  (%.1f ms): %s",
            request.method,
            request.url.path,
            elapsed_ms,
            exc,
        )
        raise


# ---------------------------------------------------------------------------
# Global unhandled-exception handler
# ---------------------------------------------------------------------------

@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Catch any exception that escapes a route and log it with a full traceback.

    Returns a structured JSON 500 so the frontend always gets parseable JSON.
    """
    tb = traceback.format_exc()
    logger.error(
        "Unhandled exception on %s %s:\n%s",
        request.method,
        request.url.path,
        tb,
    )
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "detail": str(exc),
            "path": request.url.path,
        },
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    from backend.db import check_db_connection
    db_ok = check_db_connection()
    status = "ok" if db_ok else "degraded"
    logger.debug("Health check — db_ok=%s", db_ok)
    return {
        "status": status,
        "service": "shield-ai",
        "version": "0.2.0",
        "db": "connected" if db_ok else "unreachable",
    }


app.include_router(contracts.router, prefix="/contracts", tags=["contracts"])
app.include_router(query.router, prefix="/query", tags=["query"])
app.include_router(graph.router, prefix="/graph", tags=["graph"])
app.include_router(rag.router, prefix="/rag", tags=["rag"])
app.include_router(audit_logs.router, prefix="/audit", tags=["audit"])
app.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
