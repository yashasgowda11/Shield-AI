"""Pinecone index wrapper.

Two namespaces inside one Pinecone index:
  - "contracts" : past contracts, clause-level
  - "policies"  : HIPAA / SOC2 / GDPR policy snippets

Pinecone persists vectors permanently — no rebuild on restart, no pickle cache.
The same interface (search, __len__) is preserved so agents and retrieve.py
are unchanged.

Configure via env:
  PINECONE_API_KEY        required
  PINECONE_INDEX_NAME     required (create this in the Pinecone console, dim=3072, cosine)
"""
import logging
import os
from typing import Any

from pinecone import Pinecone

from backend.rag.embed import EMBEDDING_DIM

logger = logging.getLogger(__name__)

_pc: Pinecone | None = None


def _get_client() -> Pinecone:
    global _pc
    if _pc is None:
        api_key = os.getenv("PINECONE_API_KEY")
        if not api_key:
            raise RuntimeError("PINECONE_API_KEY not set in environment")
        _pc = Pinecone(api_key=api_key)
    return _pc


def _get_index():
    name = os.getenv("PINECONE_INDEX_NAME")
    if not name:
        raise RuntimeError("PINECONE_INDEX_NAME not set in environment")
    return _get_client().Index(name)


class PineconeNamespace:
    """Thin wrapper around a Pinecone index namespace.

    Presents the same search() / __len__() interface as the old FAISSIndex
    so retrieve.py and the agents need no changes.
    """

    def __init__(self, namespace: str):
        self.namespace = namespace
        self._count: int = 0

    def upsert(self, vectors: list[dict]) -> None:
        """Upsert a batch of {id, values, metadata} dicts to Pinecone."""
        if not vectors:
            return
        idx = _get_index()
        # Pinecone upsert accepts batches up to 100 vectors
        batch_size = 100
        for i in range(0, len(vectors), batch_size):
            batch = vectors[i : i + batch_size]
            idx.upsert(vectors=batch, namespace=self.namespace)
        self._count += len(vectors)
        logger.info("Upserted %d vectors to namespace '%s'", len(vectors), self.namespace)

    def search(
        self, query_embedding: list[float] | Any, k: int = 5
    ) -> list[tuple[float, dict[str, Any]]]:
        """Return [(score, metadata)] sorted by similarity descending."""
        if self._count == 0:
            return []

        if hasattr(query_embedding, "tolist"):
            query_embedding = query_embedding.tolist()

        idx = _get_index()
        resp = idx.query(
            vector=query_embedding,
            top_k=k,
            namespace=self.namespace,
            include_metadata=True,
        )
        return [
            (match["score"], match.get("metadata") or {})
            for match in resp.get("matches", [])
        ]

    def count(self) -> int:
        """Live vector count from Pinecone stats."""
        try:
            idx = _get_index()
            stats = idx.describe_index_stats()
            ns = stats.get("namespaces", {}).get(self.namespace, {})
            self._count = ns.get("vector_count", 0)
        except Exception:
            logger.warning("Could not fetch Pinecone stats for namespace '%s'", self.namespace)
        return self._count

    def __len__(self) -> int:
        return self._count


# Module-level registry. Populated at startup by ingest.build_all_indices().
INDICES: dict[str, PineconeNamespace] = {}
