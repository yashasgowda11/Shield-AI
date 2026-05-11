"""Debug endpoints for the RAG layer.

  GET /rag/status             → which indices are loaded and how many entries
  GET /rag/search?q=...&source=contracts&k=5
                              → top-k results, with score + full metadata
"""
from fastapi import APIRouter, HTTPException, Query

from backend.rag.retrieve import index_status, retrieve

router = APIRouter()


@router.get("/status")
def status():
    return index_status()


@router.get("/search")
def search(
    q: str = Query(..., description="Query text"),
    source: str = Query("contracts", description="Index name: contracts | policies"),
    k: int = Query(5, ge=1, le=20),
):
    if source not in {"contracts", "policies"}:
        raise HTTPException(status_code=400, detail=f"Unknown source: {source}")
    try:
        results = retrieve(q, source=source, k=k)
    except RuntimeError as e:
        # Most commonly: GEMINI_API_KEY not configured
        raise HTTPException(status_code=503, detail=str(e))
    return {"query": q, "source": source, "k": k, "results": results}
