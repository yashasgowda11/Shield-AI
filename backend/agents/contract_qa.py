"""Contract Q&A agent — grounded NL questions about a single contract.

Sister agent to analytics.py. Where analytics answers questions about the
whole corpus via SQL, this agent answers questions about ONE contract by
stuffing all of its segmented clauses into the prompt as ground truth and
asking Gemini for a citation-grounded answer.

Why in-prompt (and not Pinecone-per-contract):
  - Contracts in scope are small (10-40 clauses, ~2-5 KB of text)
  - Cheaper: no per-upload embedding writes
  - Better grounding: the model sees every clause, so it never misses one
  - Deterministic citations: clause numbers come straight from the data we
    handed in, not from a retrieval that might miss the right one

If contracts grow much larger we can swap to per-contract Pinecone namespaces
without touching the agent's public interface.

Every Q&A persists an AgentOutput row (agent_name='contract_qa') for the
audit trail.
"""
import json
import logging
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from backend import audit
from backend.agents.schemas import ContractQAResult
from backend.llm import MODEL_FLASH, generate_json, hash_prompt
from backend.models import AgentOutput, Contract

logger = logging.getLogger(__name__)

AGENT_NAME = "contract_qa"
PROMPT_VERSION = "v1.0.0"

_PROMPT_PATH = (
    Path(__file__).resolve().parents[2] / "prompts" / f"contract_qa_{PROMPT_VERSION}.txt"
)
_PROMPT_TEMPLATE = _PROMPT_PATH.read_text(encoding="utf-8")

SYSTEM_INSTRUCTION = (
    "You are Shield AI's contract Q&A specialist. You answer questions about "
    "ONE specific contract using ONLY the clauses provided as ground truth. "
    "You never speculate, never use outside knowledge, and always cite the "
    "clause numbers that ground each factual claim. If the contract does not "
    "address the question, you say so clearly rather than guess."
)


def _format_clauses(clauses: list[dict]) -> str:
    """Render the contract's clauses as a clean ground-truth block."""
    if not clauses:
        return "  (no clauses extracted from this contract)"
    lines = []
    for c in clauses:
        number = c.get("number", "?")
        title = c.get("title", "")
        text = (c.get("text") or "").strip()
        lines.append(f"§ {number} — {title}\n  {text}")
    return "\n\n".join(lines)


def run(db: Session, contract_id: int, question: str) -> dict[str, Any]:
    """End-to-end: load contract clauses, ask Gemini, persist output, return result.

    Returns:
        {
          "contract_id": int,
          "question": str,
          "answer": str | None,
          "cited_clauses": [{number, title, relevance}, ...],
          "confidence": float | None,
          "error": str | None,
          "prompt_hash": str,
          "filename": str,
        }
    """
    contract: Contract | None = (
        db.query(Contract).filter(Contract.id == contract_id).first()
    )
    if not contract:
        return {
            "contract_id": contract_id,
            "question": question,
            "answer": None,
            "cited_clauses": [],
            "confidence": None,
            "error": f"Contract {contract_id} not found",
            "prompt_hash": None,
            "filename": None,
        }

    clauses = contract.clauses or []
    if not clauses:
        return {
            "contract_id": contract_id,
            "question": question,
            "filename": contract.filename,
            "answer": (
                "This contract has no extracted clauses yet — Q&A isn't "
                "available until the extraction agent runs."
            ),
            "cited_clauses": [],
            "confidence": 0.0,
            "error": None,
            "prompt_hash": None,
        }

    prompt = (
        _PROMPT_TEMPLATE
        .replace("{contract_filename}", contract.filename or "(unknown filename)")
        .replace("{clauses_block}", _format_clauses(clauses))
        .replace("{question}", question)
    )
    p_hash = hash_prompt(prompt, system=SYSTEM_INSTRUCTION)

    logger.info(
        "contract_qa: contract %s, %d clauses, question=%r",
        contract_id, len(clauses), question[:80],
    )

    try:
        result: ContractQAResult = generate_json(
            prompt=prompt,
            schema=ContractQAResult,
            model=MODEL_FLASH,
            system=SYSTEM_INSTRUCTION,
        )
    except Exception as e:
        logger.exception("contract_qa Gemini call failed")
        return {
            "contract_id": contract_id,
            "filename": contract.filename,
            "question": question,
            "answer": None,
            "cited_clauses": [],
            "confidence": None,
            "error": f"Q&A failed: {e}",
            "prompt_hash": p_hash,
        }

    output_dict = json.loads(result.model_dump_json())
    # Persist for audit — include the question so the audit log shows what
    # was asked, not just that the agent ran.
    db.add(AgentOutput(
        contract_id=contract_id,
        agent_name=AGENT_NAME,
        output={"question": question, **output_dict},
        confidence=result.confidence,
        prompt_hash=p_hash,
    ))
    db.commit()

    audit.log(
        db,
        actor=f"agent:{AGENT_NAME}",
        action="answer",
        resource=f"contract:{contract_id}",
        after={
            "question": question[:200],
            "n_citations": len(result.cited_clauses),
            "confidence": result.confidence,
            "prompt_hash": p_hash,
            "prompt_version": PROMPT_VERSION,
        },
    )

    return {
        "contract_id": contract_id,
        "filename": contract.filename,
        "question": question,
        "answer": result.answer,
        "cited_clauses": output_dict.get("cited_clauses", []),
        "confidence": result.confidence,
        "error": None,
        "prompt_hash": p_hash,
    }
