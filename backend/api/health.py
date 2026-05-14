"""Extended health check and data recovery endpoints."""
import logging
import os
from fastapi import APIRouter

from backend import lobstertrap as lt_client
from backend import cache as shield_cache

logger = logging.getLogger(__name__)
router = APIRouter()


def _check_pinecone() -> bool:
    if not os.getenv("PINECONE_API_KEY") or not os.getenv("PINECONE_INDEX_NAME"):
        return False
    try:
        from pinecone import Pinecone
        pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
        pc.list_indexes()
        return True
    except Exception:
        return False


@router.get("/services")
def services_status():
    """Full service health check — LT, Gemini fallback, DB, Pinecone, cache."""
    from backend.llm import get_fallback_state, MODEL_FLASH
    from backend.db import check_db_connection

    lt_ok = lt_client.is_available()
    gemini_state = get_fallback_state()
    db_ok = check_db_connection()
    pinecone_ok = _check_pinecone()
    pending = shield_cache.count()

    return {
        "lt": {
            "available": lt_ok,
            "url": lt_client.URL,
        },
        "gemini": {
            "fallback_active": gemini_state["fallback_active"],
            "model_in_use": gemini_state["model_in_use"] or MODEL_FLASH,
            "fallback_reason": gemini_state["fallback_reason"],
            "primary_model": gemini_state["primary_model"] or MODEL_FLASH,
        },
        "db": {"connected": db_ok},
        "pinecone": {"available": pinecone_ok},
        "cache_pending": pending,
    }


@router.get("/cache")
def get_cache_entries():
    """Return all pending cache entries. Admin-only (enforced in frontend)."""
    return {"entries": shield_cache.read_all(), "count": shield_cache.count()}


@router.delete("/cache/{entry_id}")
def delete_cache_entry(entry_id: str):
    """Delete a resolved cache entry."""
    deleted = shield_cache.delete(entry_id)
    if not deleted:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Entry not found")
    return {"deleted": True, "entry_id": entry_id}
