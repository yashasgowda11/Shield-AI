"""Build FAISS indices from corpus directories at startup.

Reads:
  backend/corpus/past_contracts/*.json  → INDICES["contracts"]
  backend/corpus/policies/*.json         → INDICES["policies"]

Each clause / policy snippet becomes one indexed entry. Metadata travels with
the entry so retrievers can return rich context (vendor, framework, severity, ...).
"""
import json
import logging
from pathlib import Path

from backend.rag.cache import load_or_compute
from backend.rag.embed import EMBEDDING_DIM, embed_documents
from backend.rag.index import INDICES, FAISSIndex

logger = logging.getLogger(__name__)

CORPUS_DIR = Path(__file__).resolve().parents[1] / "corpus"


def build_all_indices() -> dict[str, int]:
    """Build all indices. Returns {name: count} for logging."""
    INDICES["contracts"] = _build_contracts_index()
    INDICES["policies"] = _build_policies_index()
    counts = {k: len(v) for k, v in INDICES.items()}
    logger.info("RAG indices built: %s", counts)
    return counts


def _build_contracts_index() -> FAISSIndex:
    idx = FAISSIndex("contracts", dim=EMBEDDING_DIM)
    items: list[tuple[str, dict]] = []

    for path in sorted((CORPUS_DIR / "past_contracts").glob("*.json")):
        with path.open() as f:
            doc = json.load(f)
        for clause in doc.get("clauses", []):
            # Build the embedding text — title + body so semantic search works
            # on both topic and content
            embed_text = f"[{clause['title']}] {clause['text']}"

            # Attach risk findings for THIS clause to its metadata so the Risk
            # Agent can show "this clause is similar to clause 7.2 of HelixHealth's
            # contract, which was rated Critical for unlimited liability"
            findings = [
                f for f in doc.get("risk_findings", [])
                if f.get("clause_ref") == clause["number"]
            ]

            items.append((embed_text, {
                "source": "contracts",
                "contract_id": doc["id"],
                "vendor": doc["vendor"],
                "type": doc["type"],
                "clause_number": clause["number"],
                "clause_title": clause["title"],
                "clause_text": clause["text"],
                "approval_outcome": doc.get("approval_outcome"),
                "risk_score": doc.get("risk_score"),
                "findings_for_clause": findings,
            }))

    if not items:
        logger.warning("No past contracts found in corpus")
        return idx

    texts = [t for t, _ in items]
    metas = [m for _, m in items]
    embeddings = load_or_compute("contracts", texts, embed_documents)
    idx.add(embeddings, metas)
    logger.info("Indexed %d clauses across %d past contracts",
                len(items),
                len({m['contract_id'] for m in metas}))
    return idx


def _build_policies_index() -> FAISSIndex:
    idx = FAISSIndex("policies", dim=EMBEDDING_DIM)
    items: list[tuple[str, dict]] = []

    for path in sorted((CORPUS_DIR / "policies").glob("*.json")):
        with path.open() as f:
            doc = json.load(f)
        for snippet in doc.get("snippets", []):
            embed_text = f"[{doc['framework']} - {snippet['requirement']}] {snippet['text']}"
            items.append((embed_text, {
                "source": "policies",
                "framework": doc["framework"],
                "requirement": snippet["requirement"],
                "severity": snippet.get("severity", "medium"),
                "text": snippet["text"],
            }))

    if not items:
        logger.warning("No policy snippets found in corpus")
        return idx

    texts = [t for t, _ in items]
    metas = [m for _, m in items]
    embeddings = load_or_compute("policies", texts, embed_documents)
    idx.add(embeddings, metas)
    logger.info("Indexed %d policy snippets across %d frameworks",
                len(items),
                len({m['framework'] for m in metas}))
    return idx
