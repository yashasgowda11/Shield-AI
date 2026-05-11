"""Agent 2 — Risk Assessment (Gemini Pro + RAG over past contracts).

For each clause in the contract:
  1. Retrieve top-k similar clauses from the past_contracts FAISS index.
  2. Format them as comparators (with their prior risk findings) in the prompt.

Gemini sees ALL clauses + their respective comparators in one call and returns
a RiskAssessment (aggregate score + per-clause findings).

This is the first agent that visibly uses RAG — the "Similar prior contracts"
panel in the UI is built from the same retrievals.
"""
import json
import logging
from pathlib import Path

from sqlalchemy.orm import Session

from backend import audit
from backend.agents.schemas import RiskAssessment
from backend.llm import MODEL_PRO, generate_json, hash_prompt
from backend.models import AgentOutput
from backend.rag.retrieve import batch_retrieve, retrieve  # noqa: F401

logger = logging.getLogger(__name__)

AGENT_NAME = "risk"
PROMPT_VERSION = "v1.0.0"

_PROMPT_PATH = Path(__file__).resolve().parents[2] / "prompts" / f"risk_{PROMPT_VERSION}.txt"
_PROMPT_TEMPLATE = _PROMPT_PATH.read_text(encoding="utf-8")

SYSTEM_INSTRUCTION = (
    "You are a contract risk specialist. You identify material risks in vendor "
    "and procurement agreements, calibrating severity using prior findings from "
    "comparable contracts. You ground every finding in the actual clause text — "
    "you never invent risks."
)

SIMILAR_PER_CLAUSE = 3


def _format_comparators(similar: list[dict]) -> str:
    """Render retrieved similar clauses for the prompt."""
    if not similar:
        return "    (no comparable prior clauses found)"
    lines = []
    for i, s in enumerate(similar, 1):
        findings = s.get("findings_for_clause") or []
        if findings:
            f = findings[0]
            rating = f"prior rating: {f['severity']} for \"{f['risk']}\""
        else:
            rating = "prior rating: no risk recorded"
        lines.append(
            f"    {i}. [{s['vendor']} · clause {s['clause_number']}, {rating}]\n"
            f"       \"{s['clause_text'][:300]}\""
        )
    return "\n".join(lines)


def _format_clauses_with_comparators(clauses: list[dict]) -> str:
    """Build the clauses block of the prompt.

    Performance: batches all per-clause RAG queries into one embedding API call
    via batch_retrieve. For an 8-clause contract this turns 8 sequential
    Gemini round-trips into 1 — the single biggest latency win in the upload
    pipeline.
    """
    if not clauses:
        return ""

    try:
        all_similar = batch_retrieve(
            [c["text"] for c in clauses],
            source="contracts",
            k=SIMILAR_PER_CLAUSE,
        )
    except Exception:
        logger.exception(
            "Batch RAG retrieve failed; continuing without comparators",
        )
        all_similar = [[] for _ in clauses]

    sections = []
    for c, similar in zip(clauses, all_similar):
        sections.append(
            f"Clause {c['number']} — {c.get('title', '')}\n"
            f"  {c['text']}\n\n"
            f"  Similar prior clauses:\n{_format_comparators(similar)}"
        )
    return "\n\n---\n\n".join(sections)


def run(db: Session, contract_id: int, clauses: list[dict]) -> RiskAssessment:
    """Execute Agent 2."""
    if not clauses:
        # No clauses → nothing to assess. Still persist a row so downstream
        # knows the agent ran.
        result = RiskAssessment(score=0, findings=[])
        p_hash = None
    else:
        clauses_block = _format_clauses_with_comparators(clauses)
        prompt = _PROMPT_TEMPLATE.format(clauses_with_comparators=clauses_block)
        p_hash = hash_prompt(prompt, system=SYSTEM_INSTRUCTION)

        logger.info(
            "Running Agent 2 (risk) on contract %s with %d clauses",
            contract_id, len(clauses),
        )
        result = generate_json(
            prompt=prompt,
            schema=RiskAssessment,
            model=MODEL_PRO,
            system=SYSTEM_INSTRUCTION,
        )

    output_dict = json.loads(result.model_dump_json())
    db.add(AgentOutput(
        contract_id=contract_id,
        agent_name=AGENT_NAME,
        output=output_dict,
        confidence=None,
        prompt_hash=p_hash,
    ))
    db.commit()

    audit.log(
        db,
        actor=f"agent:{AGENT_NAME}",
        action="assess",
        resource=f"contract:{contract_id}",
        after={
            "score": result.score,
            "n_findings": len(result.findings),
            "prompt_hash": p_hash,
            "prompt_version": PROMPT_VERSION,
        },
    )
    return result
