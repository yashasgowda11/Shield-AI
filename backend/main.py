"""FastAPI app entry point.

Run with: uvicorn backend.main:app --reload --port 8000
Docs at: http://localhost:8000/docs

Set SKIP_RAG_INIT=true in .env to skip embedding the corpus on boot
(useful during fast iteration when you don't need RAG features).
"""
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api import audit_logs, contracts, dashboard, graph, query, rag
from backend.db import init_db

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ---- Startup ----
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

    yield
    # ---- Shutdown ----


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


@app.get("/health")
def health():
    return {"status": "ok", "service": "shield-ai", "version": "0.2.0"}


app.include_router(contracts.router, prefix="/contracts", tags=["contracts"])
app.include_router(query.router, prefix="/query", tags=["query"])
app.include_router(graph.router, prefix="/graph", tags=["graph"])
app.include_router(rag.router, prefix="/rag", tags=["rag"])
app.include_router(audit_logs.router, prefix="/audit", tags=["audit"])
app.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
