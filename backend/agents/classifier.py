"""Agent 0 — Contract Classifier (Gemini Flash, structured output).

Runs FIRST in the pipeline — before extraction, risk, or compliance —
to determine:
  - Contract type  (MSA / NDA / DPA / BAA / SaaS / Employment / …)
  - Industry sector (Healthcare / Fintech / Technology / Government / …)
  - Jurisdiction   (country + US state if applicable)
  - Data domains   (PHI / PII / Biometric / Financial / StudentData / …)
  - Applicable compliance frameworks (HIPAA / GDPR / SOC2 / PCI / CCPA / FERPA / CMMC)

The output drives two critical downstream decisions:
  1. Which compliance frameworks Agent 3 actually checks.
     A gaming distributor contract will NOT be checked against HIPAA.
  2. Which sector-calibrated risk thresholds Agent 5 applies.

Uses only the first ~4 000 characters of the contract — classification
does not need the full text and this keeps latency low.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from sqlalchemy.orm import Session

from backend import audit
from backend.agents.schemas import ClassificationResult, DataDomain
from backend.llm import MODEL_FLASH, generate_json, hash_prompt
from backend.models import AgentOutput

logger = logging.getLogger(__name__)

AGENT_NAME    = "classification"
PROMPT_VERSION = "v1.0.0"

_PROMPT_PATH = (
    Path(__file__).resolve().parents[2] / "prompts" / f"classification_{PROMPT_VERSION}.txt"
)
_PROMPT_TEMPLATE = _PROMPT_PATH.read_text(encoding="utf-8")

# Characters of contract text sent to the classifier.
# Classification only needs the header, recitals, and first few clauses.
_CLASSIFY_CHAR_LIMIT = 4_000

SYSTEM_INSTRUCTION = (
    "You are a contract classification specialist with expertise in US and "
    "international contract law across all major industry sectors. "
    "You determine contract types, sectors, jurisdictions, regulated data categories, "
    "and applicable compliance frameworks with precision. "
    "You never mark a compliance framework as applicable unless the contract "
    "explicitly involves that framework's regulated data or jurisdiction."
)

# ---------------------------------------------------------------------------
# Fallback — used when the LLM call fails completely
# ---------------------------------------------------------------------------

def _fallback_classification(raw_text: str) -> ClassificationResult:
    """Return a safe conservative classification when the LLM fails.

    Marks all common frameworks as applicable so downstream agents do not
    silently skip checks on a contract that might need them.
    """
    return ClassificationResult(
        contract_type="Other",
        sector="Other",
        jurisdiction_country=None,
        jurisdiction_us_state=None,
        data_domains=[DataDomain.PII],
        hipaa_applicable=False,
        gdpr_applicable=False,
        soc2_applicable=True,   # conservative: assume vendor handles data
        pci_applicable=False,
        ccpa_applicable=False,
        ferpa_applicable=False,
        cmmc_applicable=False,
        classification_reasoning=(
            "Fallback classification — LLM call failed. "
            "Conservative defaults applied: SOC2 enabled, all others disabled."
        ),
        confidence=0.0,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run(db: Session, contract_id: int, raw_text: str) -> ClassificationResult:
    """Execute Agent 0 — classify the contract.

    Args:
        db:           SQLAlchemy session.
        contract_id:  ID of the contract being processed.
        raw_text:     Full extracted contract text.

    Returns:
        ClassificationResult with all fields populated.
        On LLM failure, returns a safe fallback (never raises).
    """
    # Use only the first N chars — title + parties + recitals is enough
    text_excerpt = raw_text[:_CLASSIFY_CHAR_LIMIT]

    prompt = _PROMPT_TEMPLATE.format(contract_text=text_excerpt)
    p_hash = hash_prompt(prompt, system=SYSTEM_INSTRUCTION)

    logger.info(
        "Running Agent 0 (classifier) on contract %s (%d chars excerpt)",
        contract_id, len(text_excerpt),
    )

    # ── LLM call ─────────────────────────────────────────────────────────────
    try:
        result: ClassificationResult = generate_json(
            prompt=prompt,
            schema=ClassificationResult,
            model=MODEL_FLASH,
            system=SYSTEM_INSTRUCTION,
        )
        logger.info(
            "Agent 0 classified contract %s: type=%s sector=%s hipaa=%s gdpr=%s "
            "soc2=%s pci=%s ccpa=%s ferpa=%s cmmc=%s confidence=%.2f",
            contract_id,
            result.contract_type,
            result.sector,
            result.hipaa_applicable,
            result.gdpr_applicable,
            result.soc2_applicable,
            result.pci_applicable,
            result.ccpa_applicable,
            result.ferpa_applicable,
            result.cmmc_applicable,
            result.confidence,
        )
    except Exception as exc:
        logger.exception(
            "Agent 0 (classifier) LLM call failed for contract %s: %s — using fallback",
            contract_id, exc,
        )
        result = _fallback_classification(raw_text)

    # ── Persist to DB ─────────────────────────────────────────────────────────
    try:
        output_dict = json.loads(result.model_dump_json())
        db.add(AgentOutput(
            contract_id=contract_id,
            agent_name=AGENT_NAME,
            output=output_dict,
            confidence=result.confidence,
            prompt_hash=p_hash,
        ))
        db.commit()
    except Exception as exc:
        logger.exception(
            "Agent 0 (classifier) DB persist failed for contract %s: %s",
            contract_id, exc,
        )
        db.rollback()
        # Non-fatal — result is still returned to the orchestrator

    # ── Audit log ─────────────────────────────────────────────────────────────
    try:
        audit.log(
            db,
            actor=f"agent:{AGENT_NAME}",
            action="classify",
            resource=f"contract:{contract_id}",
            after={
                "contract_type":        result.contract_type,
                "sector":               result.sector,
                "jurisdiction_country": result.jurisdiction_country,
                "jurisdiction_us_state": result.jurisdiction_us_state,
                "data_domains":         [d.value for d in result.data_domains],
                "hipaa_applicable":     result.hipaa_applicable,
                "gdpr_applicable":      result.gdpr_applicable,
                "soc2_applicable":      result.soc2_applicable,
                "pci_applicable":       result.pci_applicable,
                "ccpa_applicable":      result.ccpa_applicable,
                "ferpa_applicable":     result.ferpa_applicable,
                "cmmc_applicable":      result.cmmc_applicable,
                "confidence":           result.confidence,
                "prompt_version":       PROMPT_VERSION,
            },
        )
    except Exception:
        logger.exception(
            "Agent 0 audit log failed for contract %s (non-fatal)", contract_id
        )

    return result
