"""Tests for the RAG layer.

Embedding API calls are skipped (network + cost). Instead we test the FAISS
wrapper with synthetic vectors and verify ingest can read the corpus shape.
"""
import os

import numpy as np
import pytest

# Don't actually call Gemini in tests
os.environ["SKIP_RAG_INIT"] = "true"

from backend.rag.index import FAISSIndex


def test_faiss_index_basic_search():
    idx = FAISSIndex("test", dim=4)
    vectors = np.array([
        [1.0, 0.0, 0.0, 0.0],
        [0.0, 1.0, 0.0, 0.0],
        [0.7, 0.7, 0.0, 0.0],
        [0.0, 0.0, 1.0, 0.0],
    ], dtype=np.float32)
    metas = [{"id": i} for i in range(4)]
    idx.add(vectors, metas)

    # Query close to vector 0; expect 0 first, then 2 (which has component along axis 0)
    results = idx.search(np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32), k=4)
    assert len(results) == 4
    assert results[0][1]["id"] == 0
    # Second-best should share a component with the query
    assert results[1][1]["id"] == 2


def test_faiss_index_empty_search_returns_empty():
    idx = FAISSIndex("empty", dim=4)
    results = idx.search(np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32))
    assert results == []


def test_faiss_index_dim_mismatch_raises():
    idx = FAISSIndex("test", dim=4)
    with pytest.raises(ValueError):
        idx.add(np.zeros((2, 5), dtype=np.float32), [{}, {}])


def test_faiss_index_meta_mismatch_raises():
    idx = FAISSIndex("test", dim=4)
    with pytest.raises(ValueError):
        idx.add(np.zeros((2, 4), dtype=np.float32), [{}])


def test_faiss_index_k_clamped_to_size():
    idx = FAISSIndex("test", dim=4)
    idx.add(np.eye(2, 4, dtype=np.float32), [{"id": 0}, {"id": 1}])
    results = idx.search(np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32), k=10)
    assert len(results) == 2  # not 10


def test_batch_retrieve_returns_empty_list_per_query_when_index_missing():
    """If RAG isn't loaded, batch_retrieve should return [[], [], ...]
    matching input length — not raise."""
    from backend.rag.index import INDICES
    from backend.rag.retrieve import batch_retrieve
    INDICES.clear()  # ensure no index loaded
    results = batch_retrieve(["q1", "q2", "q3"], source="contracts", k=3)
    assert results == [[], [], []]


def test_batch_retrieve_returns_empty_when_no_queries():
    from backend.rag.retrieve import batch_retrieve
    assert batch_retrieve([], source="contracts") == []


def test_batch_retrieve_uses_one_embedding_call(monkeypatch):
    """The whole point of batch_retrieve: N queries → 1 embed call."""
    import numpy as np

    from backend.rag.index import INDICES, FAISSIndex

    # Seed a small index
    idx = FAISSIndex("contracts", dim=4)
    idx.add(np.eye(3, 4, dtype=np.float32),
            [{"contract_id": f"C{i}"} for i in range(3)])
    INDICES["contracts"] = idx

    # Mock embed_queries to count calls and return synthetic vectors
    call_count = {"n": 0}

    def fake_embed_queries(texts):
        call_count["n"] += 1
        return np.array([[1.0, 0, 0, 0]] * len(texts), dtype=np.float32)

    monkeypatch.setattr("backend.rag.retrieve.embed_queries", fake_embed_queries)

    from backend.rag.retrieve import batch_retrieve
    results = batch_retrieve(["q1", "q2", "q3", "q4"], source="contracts", k=2)

    assert call_count["n"] == 1, "batch_retrieve should make exactly 1 embed call"
    assert len(results) == 4
    for r in results:
        assert len(r) == 2  # k=2
    INDICES.clear()


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
