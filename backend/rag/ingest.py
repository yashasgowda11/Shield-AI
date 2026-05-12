"""Build Pinecone indices from corpus directories at startup.

Reads:
  backend/corpus/past_contracts/*.json  → namespace "contracts"
  backend/corpus/policies/*.json        → namespace "policies"

Vectors are upserted with a deterministic ID derived from source + position.
If the vectors are already present (same ID), Pinecone skips them — so
restarting the backend never re-embeds or re-charges the API.

Each clause / policy snippet becomes one indexed vector. Metadata travels
with the vector so retrievers can return rich context (vendor, framework,
severity, ...).
"""
import hashlib
import json
import logging
from pathlib import Path

from backend.rag.embed import embed_documents
from backend.rag.index import INDICES, PineconeNamespace

logger = logging.getLogger(__name__)

CORPUS_DIR = Path(__file__).resolve().parents[1] / "corpus"


def _vector_id(namespace: str, *parts: str) -> str:
    """Stable deterministic ID for a vector so upserts are idempotent."""
    raw = f"{namespace}:" + ":".join(parts)
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def build_all_indices() -> dict[str, int]:
    """Build all indices. Returns {namespace: count} for logging."""
    INDICES["contracts"] = _build_contracts_index()
    INDICES["policies"] = _build_policies_index()
    counts = {k: v.count() for k, v in INDICES.items()}
    logger.info("Pinecone indices ready: %s", counts)
    return counts


def _build_contracts_index() -> PineconeNamespace:
    ns = PineconeNamespace("contracts")
    items: list[tuple[str, str, dict]] = []  # (vector_id, embed_text, metadata)

    for path in sorted((CORPUS_DIR / "past_contracts").glob("*.json")):
        with path.open() as f:
            doc = json.load(f)
        for clause in doc.get("clauses", []):
            embed_text = f"[{clause['title']}] {clause['text']}"
            findings = [
                f for f in doc.get("risk_findings", [])
                if f.get("clause_ref") == clause["number"]
            ]
            vid = _vector_id("contracts", doc["id"], str(clause["number"]))
            items.append((vid, embed_text, {
                "source": "contracts",
                "contract_id": doc["id"],
                "vendor": doc["vendor"],
                "type": doc["type"],
                "clause_number": str(clause["number"]),
                "clause_title": clause["title"],
                "clause_text": clause["text"][:1000],  # Pinecone metadata limit
                "approval_outcome": doc.get("approval_outcome", ""),
                "risk_score": str(doc.get("risk_score", "")),
                "findings_for_clause": json.dumps(findings),  # nested → JSON string
            }))

    if not items:
        logger.warning("No past contracts found in corpus")
        return ns

    # Check live count — skip embedding if already indexed
    existing = ns.count()
    if existing >= len(items):
        logger.info(
            "Pinecone 'contracts' namespace already has %d vectors (corpus=%d) — skipping upsert",
            existing, len(items),
        )
        return ns

    logger.info("Embedding %d contract clauses and upserting to Pinecone...", len(items))
    texts = [t for _, t, _ in items]
    embeddings = embed_documents(texts)

    vectors = [
        {"id": vid, "values": embeddings[i].tolist(), "metadata": meta}
        for i, (vid, _, meta) in enumerate(items)
    ]
    ns.upsert(vectors)
    logger.info("Indexed %d clauses from %d past contracts",
                len(items), len({m[2]["contract_id"] for m in items}))
    return ns


def _build_policies_index() -> PineconeNamespace:
    ns = PineconeNamespace("policies")
    items: list[tuple[str, str, dict]] = []

    for path in sorted((CORPUS_DIR / "policies").glob("*.json")):
        with path.open() as f:
            doc = json.load(f)
        for i, snippet in enumerate(doc.get("snippets", [])):
            embed_text = f"[{doc['framework']} - {snippet['requirement']}] {snippet['text']}"
            vid = _vector_id("policies", doc["framework"], str(i))
            items.append((vid, embed_text, {
                "source": "policies",
                "framework": doc["framework"],
                "requirement": snippet["requirement"],
                "severity": snippet.get("severity", "medium"),
                "text": snippet["text"][:1000],
            }))

    if not items:
        logger.warning("No policy snippets found in corpus")
        return ns

    existing = ns.count()
    if existing >= len(items):
        logger.info(
            "Pinecone 'policies' namespace already has %d vectors (corpus=%d) — skipping upsert",
            existing, len(items),
        )
        return ns

    logger.info("Embedding %d policy snippets and upserting to Pinecone...", len(items))
    texts = [t for _, t, _ in items]
    embeddings = embed_documents(texts)

    vectors = [
        {"id": vid, "values": embeddings[i].tolist(), "metadata": meta}
        for i, (vid, _, meta) in enumerate(items)
    ]
    ns.upsert(vectors)
    logger.info("Indexed %d policy snippets across %d frameworks",
                len(items), len({m[2]["framework"] for m in items}))
    return ns


def upsert_contract_clauses(
    contract_id: int,
    vendor: str,
    clauses: list[dict],
    risk_findings: list[dict] | None = None,
    approval_outcome: str = "processed",
    risk_score: int | None = None,
) -> int:
    """Add an uploaded contract's clauses to the Pinecone contracts namespace.

    Called automatically after the agent pipeline finishes so every processed
    contract becomes a comparator for future risk assessments.

    Args:
        contract_id:      DB primary key of the contract.
        vendor:           Vendor name extracted by Agent 1.
        clauses:          Segmented clause list from contract.clauses.
        risk_findings:    Finding dicts from Agent 2's risk output (optional).
        approval_outcome: Final AI recommendation status (e.g. "approved",
                          "manager_review", "legal_review", "rejected").
        risk_score:       Overall risk score from Agent 2 (optional).

    Returns:
        Number of vectors upserted (0 if index not loaded or no clauses).
    """
    ns = INDICES.get("contracts")
    if ns is None:
        logger.warning(
            "Contracts index not initialised — skipping upsert for contract %s", contract_id
        )
        return 0

    if not clauses:
        logger.warning("No clauses to index for contract %s", contract_id)
        return 0

    findings = risk_findings or []
    items: list[tuple[str, str, dict]] = []

    for clause in clauses:
        embed_text = f"[{clause.get('title', '')}] {clause.get('text', '')}"
        clause_findings = [
            f for f in findings if f.get("clause_ref") == clause.get("number")
        ]
        vid = _vector_id("contracts", f"uploaded_{contract_id}", str(clause.get("number", 0)))
        items.append((vid, embed_text, {
            "source": "contracts",
            "contract_id": f"uploaded_{contract_id}",
            "vendor": vendor,
            "type": "uploaded",
            "clause_number": str(clause.get("number", "")),
            "clause_title": clause.get("title", ""),
            "clause_text": clause.get("text", "")[:1000],
            "approval_outcome": approval_outcome,
            "risk_score": str(risk_score) if risk_score is not None else "",
            "findings_for_clause": json.dumps(clause_findings),
        }))

    if not items:
        return 0

    logger.info(
        "Embedding %d clause vectors for contract %s (vendor='%s', outcome='%s') → Pinecone",
        len(items), contract_id, vendor, approval_outcome,
    )

    try:
        texts = [t for _, t, _ in items]
        embeddings = embed_documents(texts)
        vectors = [
            {"id": vid, "values": embeddings[i].tolist(), "metadata": meta}
            for i, (vid, _, meta) in enumerate(items)
        ]
        ns.upsert(vectors)
        logger.info(
            "Successfully indexed %d clause vectors for contract %s into Pinecone",
            len(vectors), contract_id,
        )
        return len(vectors)
    except Exception as exc:
        logger.exception(
            "Failed to upsert contract %s clauses to Pinecone: %s", contract_id, exc
        )
        raise
