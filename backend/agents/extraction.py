"""Agent 1 — Document Extraction (Gemini Flash, structured output).

Takes raw contract text, returns parties / dates / term / payment_terms /
governing_law / obligations / summary as a Pydantic-validated object.

Persists the output (and prompt hash) to agent_outputs for the audit trail.
"""
import json
import logging
from pathlib import Path

from sqlalchemy.orm import Session

from backend import audit
from backend.agents.schemas import ExtractionResult
from backend.llm import MODEL_FLASH, generate_json, hash_prompt
from backend.models import AgentOutput

logger = logging.getLogger(__name__)

AGENT_NAME = "extraction"
PROMPT_VERSION = "v1.0.0"

# Load the prompt template once at import time
_PROMPT_PATH = Path(__file__).resolve().parents[2] / "prompts" / f"extraction_{PROMPT_VERSION}.txt"
_PROMPT_TEMPLATE = _PROMPT_PATH.read_text(encoding="utf-8")

SYSTEM_INSTRUCTION = (
    "You are a contract extraction specialist. You extract structured information "
    "from legal agreements with precision. You never invent facts. When a field is "
    "not present in the text, you return null."
)


def run(
    db: Session,
    contract_id: int,
    raw_text: str,
    clauses: list[dict] | None = None,  # currently unused; reserved for future grounding
) -> ExtractionResult:
    """Execute Agent 1.

    Args:
        db: SQLAlchemy session.
        contract_id: ID of the contract row to attach output to.
        raw_text: Full extracted contract text.
        clauses: Pre-segmented clauses (optional, future use).

    Returns:
        Parsed ExtractionResult.

    Side effects:
        - Writes one AgentOutput row.
        - Writes one audit_log entry.
    """
    prompt = _PROMPT_TEMPLATE.format(contract_text=raw_text)
    p_hash = hash_prompt(prompt, system=SYSTEM_INSTRUCTION)

    logger.info("Running Agent 1 (extraction) on contract %s", contract_id)

    result: ExtractionResult = generate_json(
        prompt=prompt,
        schema=ExtractionResult,
        model=MODEL_FLASH,
        system=SYSTEM_INSTRUCTION,
    )

    # Persist
    output_dict = json.loads(result.model_dump_json())
    db.add(AgentOutput(
        contract_id=contract_id,
        agent_name=AGENT_NAME,
        output=output_dict,
        confidence=None,  # Agent 1 doesn't self-report confidence yet
        prompt_hash=p_hash,
    ))
    db.commit()

    audit.log(
        db,
        actor=f"agent:{AGENT_NAME}",
        action="extract",
        resource=f"contract:{contract_id}",
        after={
            "n_parties": len(result.parties),
            "n_obligations": len(result.obligations),
            "prompt_hash": p_hash,
            "prompt_version": PROMPT_VERSION,
        },
    )
    return result
