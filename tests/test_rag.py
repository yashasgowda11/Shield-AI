"""Tests for the RAG layer.

After the Pinecone migration, the FAISS-specific unit tests were dropped —
they were testing FAISS internals, not our code. What we test now:

  - Our retrieve.py / batch_retrieve wrapper behavior, with a fake namespace
    that mimics PineconeNamespace's (search, __len__, count) interface.
  - That the corpus on disk has the shape ingest expects.

No real Pinecone or Gemini calls are made.
"""
import os
from typing import Any

# Don't actually call Gemini in tests (or hit Pinecone)
os.environ["SKIP_RAG_INIT"] = "true"


class _FakeNamespace:
    """In-memory stand-in for PineconeNamespace.

    Same (search, count, __len__) interface so retrieve.py can't tell the
    difference. Similarity = dot product on the supplied vectors.
    """

    def __init__(self, items: list[tuple[list[float], dict[str, Any]]] | None = None):
        self._items = list(items or [])

    def search(self, query_vec, k: int = 5):
        if not self._items:
            return []
        q = list(query_vec.tolist() if hasattr(query_vec, "tolist") else query_vec)
        scored = []
        for vec, meta in self._items:
            score = sum(a * b for a, b in zip(q, vec))
            scored.append((float(score), meta))
        scored.sort(key=lambda x: -x[0])
        return scored[:k]

    def count(self) -> int:
        return len(self._items)

    def __len__(self) -> int:
        return len(self._items)


# ─── retrieve.py / batch_retrieve ───────────────────────────────────────────

def test_batch_retrieve_returns_empty_list_per_query_when_index_missing():
    """If the namespace isn't loaded, batch_retrieve returns [[], [], ...] —
    same length as the input, no raise."""
    from backend.rag.index import INDICES
    from backend.rag.retrieve import batch_retrieve

    INDICES.clear()
    results = batch_retrieve(["q1", "q2", "q3"], source="contracts", k=3)
    assert results == [[], [], []]


def test_batch_retrieve_returns_empty_when_no_queries():
    from backend.rag.retrieve import batch_retrieve
    assert batch_retrieve([], source="contracts") == []


def test_batch_retrieve_uses_one_embedding_call(monkeypatch):
    """The whole point of batch_retrieve: N queries → 1 embed call."""
    import numpy as np

    from backend.rag.index import INDICES

    # Seed the registry with a fake namespace
    fake = _FakeNamespace(items=[
        ([1.0, 0.0, 0.0, 0.0], {"contract_id": "C0"}),
        ([0.0, 1.0, 0.0, 0.0], {"contract_id": "C1"}),
        ([0.0, 0.0, 1.0, 0.0], {"contract_id": "C2"}),
    ])
    INDICES["contracts"] = fake

    call_count = {"n": 0}

    def fake_embed_queries(texts):
        call_count["n"] += 1
        return np.array([[1.0, 0.0, 0.0, 0.0]] * len(texts), dtype=np.float32)

    monkeypatch.setattr("backend.rag.retrieve.embed_queries", fake_embed_queries)

    from backend.rag.retrieve import batch_retrieve
    results = batch_retrieve(["q1", "q2", "q3", "q4"], source="contracts", k=2)

    assert call_count["n"] == 1, "batch_retrieve should make exactly 1 embed call"
    assert len(results) == 4
    for r in results:
        assert len(r) == 2
        # Top hit for our query vec should be C0 (perfect dot product)
        assert r[0]["contract_id"] == "C0"

    INDICES.clear()


def test_retrieve_returns_empty_when_namespace_missing():
    from backend.rag.index import INDICES
    from backend.rag.retrieve import retrieve

    INDICES.clear()
    assert retrieve("anything", source="contracts") == []


def test_retrieve_deserializes_json_string_metadata(monkeypatch):
    """Pinecone stringifies nested dicts on upsert. retrieve should parse
    findings_for_clause back to a list."""
    import numpy as np

    from backend.rag.index import INDICES

    fake = _FakeNamespace(items=[
        ([1.0, 0.0], {
            "contract_id": "C1",
            "findings_for_clause": '[{"severity": "High", "risk": "unlimited liability"}]',
        }),
    ])
    INDICES["contracts"] = fake

    monkeypatch.setattr(
        "backend.rag.retrieve.embed_query",
        lambda text: np.array([1.0, 0.0], dtype=np.float32),
    )

    from backend.rag.retrieve import retrieve
    results = retrieve("anything", source="contracts", k=1)
    assert len(results) == 1
    findings = results[0]["findings_for_clause"]
    assert isinstance(findings, list)
    assert findings[0]["risk"] == "unlimited liability"

    INDICES.clear()


# ─── Corpus shape ────────────────────────────────────────────────────────────

def test_corpus_files_are_present_and_well_formed():
    """Sanity check that the corpus exists and has the shape ingest expects."""
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "backend" / "corpus"
    contracts = list((root / "past_contracts").glob("*.json"))
    policies = list((root / "policies").glob("*.json"))

    assert len(contracts) >= 6, "expected at least 6 past contracts"
    assert len(policies) == 3, "expected hipaa.json, soc2.json, gdpr.json"

    for path in contracts:
        with path.open() as f:
            doc = json.load(f)
        assert "id" in doc and "vendor" in doc and "clauses" in doc
        assert len(doc["clauses"]) >= 1
        for c in doc["clauses"]:
            assert "number" in c and "title" in c and "text" in c

    for path in policies:
        with path.open() as f:
            doc = json.load(f)
        assert "framework" in doc and "snippets" in doc
        assert len(doc["snippets"]) >= 5
