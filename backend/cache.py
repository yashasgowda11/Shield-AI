"""Write-ahead cache for failed DB / Pinecone writes.

When the primary datastore is unreachable, critical data is written here
instead of being silently dropped. Each entry is a separate JSON file for
atomic writes and independent retry.

Cache dir defaults to `cache/` in the working directory. Override with
SHIELD_CACHE_DIR env var.
"""
import json, logging, os, pathlib, threading, time, uuid
from typing import Any

logger = logging.getLogger(__name__)
CACHE_DIR = pathlib.Path(os.getenv("SHIELD_CACHE_DIR", "cache"))
_lock = threading.Lock()


def _ensure_dir() -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)


def write(entity_type: str, data: dict[str, Any], *, source: str = "unknown", error: str | None = None) -> str:
    """Persist a failed write. Returns the entry_id."""
    _ensure_dir()
    entry_id = str(uuid.uuid4())
    entry = {
        "id": entry_id,
        "entity_type": entity_type,
        "source": source,
        "error": error,
        "timestamp": time.time(),
        "timestamp_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "data": data,
        "retried": False,
        "retry_count": 0,
    }
    path = CACHE_DIR / f"{entry_id}.json"
    tmp = CACHE_DIR / f"{entry_id}.tmp"
    with _lock:
        tmp.write_text(json.dumps(entry, indent=2, default=str), encoding="utf-8")
        tmp.rename(path)
    logger.warning("Cache write: entity_type=%s source=%s id=%s", entity_type, source, entry_id)
    return entry_id


def read_all() -> list[dict[str, Any]]:
    """All cached entries, newest-first."""
    if not CACHE_DIR.exists():
        return []
    entries = []
    for p in CACHE_DIR.glob("*.json"):
        try:
            entries.append(json.loads(p.read_text(encoding="utf-8")))
        except Exception:
            logger.warning("Cache: could not read %s", p)
    entries.sort(key=lambda e: e.get("timestamp", 0), reverse=True)
    return entries


def count() -> int:
    if not CACHE_DIR.exists():
        return 0
    return sum(1 for _ in CACHE_DIR.glob("*.json"))


def delete(entry_id: str) -> bool:
    path = CACHE_DIR / f"{entry_id}.json"
    try:
        path.unlink()
        return True
    except FileNotFoundError:
        return False
    except Exception as exc:
        logger.error("Cache: delete failed %s: %s", entry_id, exc)
        return False


def mark_retried(entry_id: str, success: bool, result: str | None = None) -> None:
    path = CACHE_DIR / f"{entry_id}.json"
    if not path.exists():
        return
    with _lock:
        try:
            entry = json.loads(path.read_text(encoding="utf-8"))
            entry["retried"] = True
            entry["retry_count"] = entry.get("retry_count", 0) + 1
            entry["last_retry_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            entry["last_retry_success"] = success
            if result:
                entry["last_retry_result"] = result
            path.write_text(json.dumps(entry, indent=2, default=str), encoding="utf-8")
        except Exception as exc:
            logger.error("Cache: mark_retried failed %s: %s", entry_id, exc)
