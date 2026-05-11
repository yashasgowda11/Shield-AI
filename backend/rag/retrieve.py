"""Retrieval helpers used by Agents 2 (Risk) and 3 (Compliance)
and the "Similar prior contracts" UI panel.
"""
from typing import Any

from backend.rag.embed import embed_queries, embed_query
from backend.rag.index import INDICES


def retrieve(query: str, source: str, k: int = 5) -> list[dict[str, Any]]:
    """Retrieve top-k snippets from a named index.

    Args:
        query: free-text query (will be embedded with retrieval_query task type).
        source: "contracts" | "policies".
        k: how many results to return.

    Returns:
        List of metadata dicts with a "score" key prepended (cosine similarity).
        Empty list if the source isn't loaded or has no entries.
    """
    idx = INDICES.get(source)
    if idx is None or len(idx) == 0:
        return []

    q_emb = embed_query(query)
    results = idx.search(q_emb, k=k)
    return [{"score": s, **meta} for s, meta in results]


def batch_retrieve(
    queries: list[str], source: str, k: int = 5
) -> list[list[dict[str, Any]]]:
    """Batch version of retrieve. ONE embedding API call, N FAISS searches.

    Used by the Risk Agent to retrieve comparators for all clauses in a single
    network round-trip instead of N. Order of results matches order of queries.

    Returns:
        List of lists, length = len(queries). Each inner list is the same
        format as retrieve() returns. Empty inner lists if the source isn't
        loaded.
    """
    if not queries:
        return []
    idx = INDICES.get(source)
    if idx is None or len(idx) == 0:
        return [[] for _ in queries]

    embeddings = embed_queries(queries)
    out: list[list[dict[str, Any]]] = []
    for emb in embeddings:
        results = idx.search(emb, k=k)
        out.append([{"score": s, **meta} for s, meta in results])
    return out


def index_status() -> dict[str, int]:
    """For the debug endpoint and tests — what's loaded and how many entries each."""
    return {name: len(idx) for name, idx in INDICES.items()}
