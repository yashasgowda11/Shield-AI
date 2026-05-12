"""Retrieval helpers used by Agents 2 (Risk) and 3 (Compliance)
and the "Similar prior contracts" UI panel.

Interface is identical to the old FAISS version — agents need no changes.
Internally queries Pinecone namespaces instead of in-memory FAISS indices.
"""
import json
from typing import Any

from backend.rag.embed import embed_queries, embed_query
from backend.rag.index import INDICES


def _deserialize_meta(meta: dict) -> dict:
    """Pinecone stores nested dicts as JSON strings — parse them back."""
    result = dict(meta)
    if "findings_for_clause" in result and isinstance(result["findings_for_clause"], str):
        try:
            result["findings_for_clause"] = json.loads(result["findings_for_clause"])
        except Exception:
            result["findings_for_clause"] = []
    return result


def retrieve(query: str, source: str, k: int = 5) -> list[dict[str, Any]]:
    """Retrieve top-k snippets from a named Pinecone namespace.

    Args:
        query: free-text query (embedded with retrieval_query task type).
        source: "contracts" | "policies".
        k: how many results to return.

    Returns:
        List of metadata dicts with a "score" key prepended.
        Empty list if the namespace isn't loaded or has no entries.
    """
    ns = INDICES.get(source)
    if ns is None or len(ns) == 0:
        return []

    q_emb = embed_query(query)
    results = ns.search(q_emb, k=k)
    return [{"score": s, **_deserialize_meta(meta)} for s, meta in results]


def batch_retrieve(
    queries: list[str], source: str, k: int = 5
) -> list[list[dict[str, Any]]]:
    """Batch version of retrieve. ONE embedding API call, N Pinecone queries.

    Used by the Risk Agent to retrieve comparators for all clauses in a single
    embedding round-trip. Order of results matches order of queries.

    Returns:
        List of lists, length = len(queries). Each inner list is the same
        format as retrieve(). Empty inner lists if the namespace isn't loaded.
    """
    if not queries:
        return []

    ns = INDICES.get(source)
    if ns is None or len(ns) == 0:
        return [[] for _ in queries]

    embeddings = embed_queries(queries)
    out: list[list[dict[str, Any]]] = []
    for emb in embeddings:
        results = ns.search(emb, k=k)
        out.append([{"score": s, **_deserialize_meta(meta)} for s, meta in results])
    return out


def index_status() -> dict[str, int]:
    """For the debug endpoint and tests — what's loaded and how many entries each."""
    return {name: ns.count() for name, ns in INDICES.items()}
