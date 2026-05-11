"""On-disk embedding cache.

Pickles (embeddings, metadatas) per index, keyed by a content hash of the
input texts. If the corpus changes, the hash changes, and we re-embed —
otherwise we load instantly from disk.

This means restarting the backend during dev/demo costs zero embedding quota
once the corpus has been built once.
"""
import hashlib
import logging
import pickle
from pathlib import Path
from typing import Callable

import numpy as np

logger = logging.getLogger(__name__)

CACHE_DIR = Path(__file__).resolve().parent / "cache"
CACHE_DIR.mkdir(exist_ok=True)


def _content_hash(texts: list[str]) -> str:
    h = hashlib.sha256()
    for t in texts:
        h.update(t.encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()[:16]


def load_or_compute(
    name: str,
    texts: list[str],
    embed_fn: Callable[[list[str]], np.ndarray],
) -> np.ndarray:
    """Return embeddings for `texts`, loading from cache when possible.

    Cache file: backend/rag/cache/<name>_<hash>.pkl
    """
    if not texts:
        return np.zeros((0, 1), dtype=np.float32)

    key = _content_hash(texts)
    cache_file = CACHE_DIR / f"{name}_{key}.pkl"

    if cache_file.exists():
        with cache_file.open("rb") as f:
            embeddings: np.ndarray = pickle.load(f)
        if embeddings.shape[0] == len(texts):
            logger.info("RAG cache HIT for '%s' (%d items, key=%s)",
                        name, len(texts), key)
            return embeddings
        # Shape mismatch — corpus changed; fall through and recompute
        logger.warning("RAG cache shape mismatch for '%s'; recomputing", name)

    logger.info("RAG cache MISS for '%s' (%d items, key=%s) — embedding now",
                name, len(texts), key)
    embeddings = embed_fn(texts)
    with cache_file.open("wb") as f:
        pickle.dump(embeddings, f)
    logger.info("RAG cache wrote %s (%.1f KB)", cache_file.name,
                cache_file.stat().st_size / 1024)
    return embeddings


def clear_cache() -> int:
    """Delete every cached embedding file. Returns count removed."""
    files = list(CACHE_DIR.glob("*.pkl"))
    for f in files:
        f.unlink()
    return len(files)
