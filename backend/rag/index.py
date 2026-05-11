"""FAISS in-memory index wrapper.

Three named indices live in this process at runtime:
  - "contracts"  : past contracts, clause-level
  - "policies"   : HIPAA / SOC2 / GDPR policy snippets
  - "regulations": (optional, future)

Uses inner product on L2-normalized vectors → equivalent to cosine similarity.
For our corpus size (~50 entries), IndexFlatIP is exact and fast.
"""
import logging
from typing import Any

import faiss
import numpy as np

from backend.rag.embed import EMBEDDING_DIM

logger = logging.getLogger(__name__)


class FAISSIndex:
    """Wraps faiss.IndexFlatIP + a parallel metadata list."""

    def __init__(self, name: str, dim: int = EMBEDDING_DIM):
        self.name = name
        self.dim = dim
        self._index = faiss.IndexFlatIP(dim)
        self._meta: list[dict[str, Any]] = []

    def add(self, embeddings: np.ndarray, metadatas: list[dict[str, Any]]) -> None:
        """Append rows. Embeddings shape: (n, dim)."""
        if embeddings.ndim != 2 or embeddings.shape[1] != self.dim:
            raise ValueError(
                f"embeddings shape {embeddings.shape} does not match dim {self.dim}"
            )
        if embeddings.shape[0] != len(metadatas):
            raise ValueError("embeddings and metadatas length mismatch")

        emb = embeddings.astype(np.float32).copy()
        faiss.normalize_L2(emb)  # in-place; safe because we copied
        self._index.add(emb)
        self._meta.extend(metadatas)

    def search(
        self, query_embedding: np.ndarray, k: int = 5
    ) -> list[tuple[float, dict[str, Any]]]:
        """Return [(score, metadata)] sorted by similarity descending."""
        if len(self._meta) == 0:
            return []

        q = query_embedding.astype(np.float32)
        if q.ndim == 1:
            q = q.reshape(1, -1)
        q = q.copy()
        faiss.normalize_L2(q)

        k = min(k, len(self._meta))
        scores, indices = self._index.search(q, k)
        return [
            (float(s), self._meta[int(i)])
            for s, i in zip(scores[0], indices[0])
            if i >= 0
        ]

    def __len__(self) -> int:
        return len(self._meta)


# Module-level registry. Populated at startup by ingest.build_all_indices().
INDICES: dict[str, FAISSIndex] = {}
