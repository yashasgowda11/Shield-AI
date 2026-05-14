"""Agent 3 — Compliance (Gemini Pro + RAG over policy corpus).

For each applicable framework (HIPAA, SOC2, GDPR, …):
  1. Check Agent 0's ClassificationResult to see if this framework applies.
     If hipaa_applicable=False, HIPAA is skipped entirely — no false positives
     on gaming distributor agreements or marketing NDAs.
  2. Retrieve the most-relevant policy snippets for THIS contract from the
     policies FAISS index.
  3. Ask Gemini to check the contract against those requirements.

Aggregates per-framework results into a single ComplianceResult.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from backend import audit
from backend.agents import history as agent_history
from backend.agents.schemas import ClassificationResult, ComplianceResult, FrameworkResult
from backend.llm import MODEL_PRO, generate_json, hash_prompt
from backend.models import AgentOutput
from backend.rag.retrieve import retrieve

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

AGENT_NAME = "compliance"
PROMPT_VERSION = "v1.1.0"  # bumped: stricter NA handling for non-healthcare/non-EU contracts

_PROMPT_PATH = Path(__file__).resolve().parents[2] / "prompts" / f"compliance_{PROMPT_VERSION}.txt"
_PROMPT_TEMPLATE = _PROMPT_PATH.read_text(encoding="utf-8")

SYSTEM_INSTRUCTION = (
    "You are a compliance specialist. You assess vendor contracts against "
    "regulatory frameworks (HIPAA, SOC2, GDPR), citing exact contract text "
    "as evidence. You never accept paraphrasing as evidence — only direct quotes."
)

# Full list of frameworks the system knows about.
# Agent 0's ClassificationResult gates which ones actually run.
ALL_FRAMEWORKS = ["HIPAA", "SOC2", "GDPR"]
SNIPPETS_PER_FRAMEWORK = 8


def _frameworks_to_run(classification: ClassificationResult | None) -> list[str]:
    """Return the list of framework names Agent 3 should actually check.

    If classification is None (Agent 0 failed), fall back to running all
    three original frameworks — conservative but safe.

    Mapping from ClassificationResult booleans to framework names:
      hipaa_applicable → "HIPAA"
      gdpr_applicable  → "GDPR"
      soc2_applicable  → "SOC2"

    PCI, CCPA, FERPA, CMMC are not yet in the RAG policy corpus so they are
    logged but not run until their policy documents are loaded (Phase 3).
    """
    if classification is None:
        logger.warning(
            "Agent 3: no classification result — running all frameworks (conservative fallback)"
        )
        return ALL_FRAMEWORKS

    active: list[str] = []
    skipped: list[str] = []

    if classification.hipaa_applicable:
        active.append("HIPAA")
    else:
        skipped.append("HIPAA")

    if classification.gdpr_applicable:
        active.append("GDPR")
    else:
        skipped.append("GDPR")

    if classification.soc2_applicable:
        active.append("SOC2")
    else:
        skipped.append("SOC2")

    # Future frameworks — log intent but don't run yet
    future_pending = []
    if classification.pci_applicable:
        future_pending.append("PCI-DSS")
    if classification.ccpa_applicable:
        future_pending.append("CCPA")
    if classification.ferpa_applicable:
        future_pending.append("FERPA")
    if classification.cmmc_applicable:
        future_pending.append("CMMC")

    if skipped:
        logger.info(
            "Agent 3: skipping %s (not applicable per Agent 0 classification)",
            skipped,
        )
    if future_pending:
        logger.info(
            "Agent 3: %s applicable but policy corpus not yet loaded — skipping for now",
            future_pending,
        )

    return active


def _format_requirements(snippets: list[dict]) -> str:
    if not snippets:
        return "  (no requirements loaded for this framework)"
    lines = []
    for i, s in enumerate(snippets, 1):
        # Use plain "Name (severity: X)" — no brackets — so the model echoes
        # the requirement name back without surrounding it in brackets.
        lines.append(
            f"  {i}. {s['requirement']}  (severity: {s.get('severity', 'medium')})\n"
            f"     {s['text']}"
        )
    return "\n".join(lines)


def _check_framework(
    framework: str,
    raw_text: str,
    vendor_history: str = "",
) -> tuple[FrameworkResult, str | None]:
    """Run compliance check for a single framework. Returns (result, prompt_hash)."""
    try:
        all_snippets = retrieve(query=raw_text[:2000], source="policies", k=20)
        snippets = [
            s for s in all_snippets if s.get("framework") == framework
        ][:SNIPPETS_PER_FRAMEWORK]
    except Exception:
        logger.exception("RAG retrieve failed for framework %s", framework)
        snippets = []

    if not snippets:
        logger.warning("No %s snippets retrieved; framework check skipped", framework)
        return (
            FrameworkResult(framework=framework, passed=True, checks=[]),
            None,
        )

    requirements_text = _format_requirements(snippets)
    base_prompt = _PROMPT_TEMPLATE.format(
        framework=framework,
        requirements_text=requirements_text,
        contract_text=raw_text,
    )
    # Append vendor compliance history so the model can calibrate severity
    prompt = (
        f"{base_prompt}\n\n"
        f"--- VENDOR COMPLIANCE HISTORY (use to calibrate severity ratings) ---\n"
        f"{vendor_history}"
    ) if vendor_history else base_prompt
    p_hash = hash_prompt(prompt, system=SYSTEM_INSTRUCTION)

    logger.info("Running Agent 3 (compliance) — framework %s, %d requirements",
                framework, len(snippets))

    result: FrameworkResult = generate_json(
        prompt=prompt,
        schema=FrameworkResult,
        model=MODEL_PRO,
        system=SYSTEM_INSTRUCTION,
    )
    # Force the framework name in case the model renamed it.
    # Also recompute `passed` deterministically from the actual check results —
    # never trust the LLM's value because Gemini frequently marks a framework
    # as passed=True even when individual checks have present=False.
    # Rule: passed=True only if ALL checks are present.
    # If no checks were loaded (no RAG snippets), treat as not applicable → True.
    computed_passed = (
        all(chk.present for chk in result.checks)
        if result.checks
        else True
    )
    if result.passed != computed_passed:
        logger.warning(
            "Agent 3: LLM set passed=%s for %s but %d/%d checks passed — "
            "overriding to passed=%s",
            result.passed, framework,
            sum(1 for c in result.checks if c.present), len(result.checks),
            computed_passed,
        )
    result = result.model_copy(update={"framework": framework, "passed": computed_passed})
    return result, p_hash


def run(
    db: Session,
    contract_id: int,
    raw_text: str,
    classification: ClassificationResult | None = None,
) -> ComplianceResult:
    """Execute Agent 3 across applicable frameworks.

    Args:
        db:             SQLAlchemy session.
        contract_id:    ID of the contract being processed.
        raw_text:       Full contract text.
        classification: Output of Agent 0. When provided, only frameworks marked
                        as applicable are checked. When None (Agent 0 failed),
                        all three original frameworks are run as a safe fallback.

    Historical awareness: reads Agent 1's output from the DB to get the
    vendor name, then prepends that vendor's past compliance track record
    to each framework prompt so recurring failures are rated more severely.
    """
    frameworks_to_check = _frameworks_to_run(classification)

    logger.info(
        "Agent 3 (compliance) — contract %s — running frameworks: %s",
        contract_id, frameworks_to_check,
    )

    framework_results: list[FrameworkResult] = []
    prompt_hashes: list[str] = []

    # ── Load vendor compliance history (best-effort) ──────────────────────────
    vendor_history_snippet = ""
    try:
        from backend.models import AgentOutput as AO
        extraction_row = (
            db.query(AO)
            .filter_by(contract_id=contract_id, agent_name="extraction")
            .order_by(AO.created_at.desc())
            .first()
        )
        if extraction_row and extraction_row.output:
            parties = extraction_row.output.get("parties") or []
            vendor_name = parties[0].get("name", "unknown") if parties else "unknown"
            vendor_history_snippet = agent_history.get_vendor_compliance_history(db, vendor_name)
            if vendor_history_snippet:
                logger.info(
                    "Agent 3: injecting compliance history for vendor '%s'", vendor_name
                )
    except Exception:
        logger.warning("Agent 3: could not load vendor compliance history (non-fatal)", exc_info=True)

    for framework in frameworks_to_check:
        try:
            result, p_hash = _check_framework(framework, raw_text, vendor_history_snippet)
            framework_results.append(result)
            if p_hash:
                prompt_hashes.append(f"{framework}:{p_hash}")
        except Exception as e:
            logger.exception("Compliance check for %s failed", framework)
            framework_results.append(FrameworkResult(
                framework=framework, passed=False, checks=[],
            ))

    final = ComplianceResult(frameworks=framework_results)

    # ---- Persist to DB ----
    try:
        output_dict = json.loads(final.model_dump_json())
        db.add(AgentOutput(
            contract_id=contract_id,
            agent_name=AGENT_NAME,
            output=output_dict,
            confidence=None,
            prompt_hash=";".join(prompt_hashes) if prompt_hashes else None,
        ))
        db.commit()
    except Exception as exc:
        logger.exception(
            "Agent 3 (compliance) DB persist failed for contract %s: %s",
            contract_id, exc,
        )
        db.rollback()
        raise

    # ---- Audit log ----
    try:
        audit.log(
            db,
            actor=f"agent:{AGENT_NAME}",
            action="check",
            resource=f"contract:{contract_id}",
            after={
                "frameworks_checked": [f.framework for f in framework_results],
                "frameworks_passed":  [f.framework for f in framework_results if f.passed],
                "frameworks_skipped": [
                    fw for fw in ALL_FRAMEWORKS if fw not in frameworks_to_check
                ],
                "classification_used": classification is not None,
                "prompt_version": PROMPT_VERSION,
            },
        )
    except Exception:
        logger.exception("Agent 3 audit log failed for contract %s (non-fatal)", contract_id)

    return final
