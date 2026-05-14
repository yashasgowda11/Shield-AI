"""Agent 1 — Document Extraction (Gemini Flash, structured output).

Takes raw contract text, returns parties / dates / term / payment_terms /
governing_law / obligations / summary as a Pydantic-validated object.

Historical awareness:
  After the first extraction pass, if the vendor has appeared in prior
  contracts, a second pass adds vendor history context so the summary
  can flag deviations (e.g. different governing law than usual).
"""
import json
import logging
from pathlib import Path

from sqlalchemy.orm import Session

from backend import audit
from backend.agents import history as agent_history
from backend.agents.schemas import ExtractionResult
from backend.llm import MODEL_FLASH, generate_json, hash_prompt
from backend.models import AgentOutput

logger = logging.getLogger(__name__)

AGENT_NAME = "extraction"
PROMPT_VERSION = "v1.0.0"

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
    clauses: list[dict] | None = None,
) -> ExtractionResult:
    """Execute Agent 1.

    Pass 1: extract structured fields from the contract text.
    Pass 2 (if vendor seen before): re-run with vendor history context so
            the summary can flag anomalies vs prior submissions.
    """
    base_prompt = _PROMPT_TEMPLATE.format(contract_text=raw_text)
    p_hash = hash_prompt(base_prompt, system=SYSTEM_INSTRUCTION)

    logger.info("Running Agent 1 (extraction) on contract %s", contract_id)

    # ── Pass 1: base extraction ───────────────────────────────────────────────
    try:
        result: ExtractionResult = generate_json(
            prompt=base_prompt,
            schema=ExtractionResult,
            model=MODEL_FLASH,
            system=SYSTEM_INSTRUCTION,
        )
    except Exception as exc:
        logger.exception(
            "Agent 1 (extraction) LLM call failed for contract %s: %s",
            contract_id, exc,
        )
        raise

    # ── Pass 2: vendor history context (best-effort, non-fatal) ──────────────
    try:
        vendor_name = result.parties[0].name if result.parties else "unknown"
        history_snippet = agent_history.get_vendor_extraction_history(db, vendor_name)
        if history_snippet:
            logger.info(
                "Agent 1: vendor '%s' seen before — re-running with history context",
                vendor_name,
            )
            history_prompt = (
                f"{base_prompt}\n\n"
                f"--- VENDOR HISTORY (for context only — do not invent facts) ---\n"
                f"{history_snippet}"
            )
            result = generate_json(
                prompt=history_prompt,
                schema=ExtractionResult,
                model=MODEL_FLASH,
                system=SYSTEM_INSTRUCTION,
            )
    except Exception:
        logger.warning(
            "Agent 1: vendor history pass failed for contract %s (non-fatal — using pass 1 result)",
            contract_id, exc_info=True,
        )

    # ── Persist to DB ─────────────────────────────────────────────────────────
    try:
        output_dict = json.loads(result.model_dump_json())
        db.add(AgentOutput(
            contract_id=contract_id,
            agent_name=AGENT_NAME,
            output=output_dict,
            confidence=None,
            prompt_hash=p_hash,
        ))
        db.commit()
    except Exception as exc:
        logger.exception(
            "Agent 1 (extraction) DB persist failed for contract %s: %s",
            contract_id, exc,
        )
        db.rollback()
        raise

    # ── Audit log ─────────────────────────────────────────────────────────────
    try:
        audit.log(
            db,
            actor=f"agent:{AGENT_NAME}",
            action="extract",
            resource=f"contract:{contract_id}",
            after={
                "n_parties":      len(result.parties),
                "n_obligations":  len(result.obligations),
                "prompt_hash":    p_hash,
                "prompt_version": PROMPT_VERSION,
            },
        )
    except Exception:
        logger.exception("Agent 1 audit log failed for contract %s (non-fatal)", contract_id)

    return result
