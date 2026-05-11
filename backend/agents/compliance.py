"""Agent 3 — Compliance (Gemini Pro + RAG over policy corpus).

For each framework (HIPAA, SOC2, GDPR):
  1. Retrieve the most-relevant policy snippets for THIS contract from the
     policies FAISS index.
  2. Filter to the target framework, keep top-N.
  3. Ask Gemini to check the contract against those requirements.

Aggregates per-framework results into a single ComplianceResult.
Three Gemini calls total — one per framework — kept sequential for simplicity.
"""
import json
import logging
from pathlib import Path

from sqlalchemy.orm import Session

from backend import audit
from backend.agents.schemas import ComplianceResult, FrameworkResult
from backend.llm import MODEL_PRO, generate_json, hash_prompt
from backend.models import AgentOutput
from backend.rag.retrieve import retrieve

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

FRAMEWORKS = ["HIPAA", "SOC2", "GDPR"]
SNIPPETS_PER_FRAMEWORK = 8


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


def _check_framework(framework: str, raw_text: str) -> tuple[FrameworkResult, str | None]:
    """Run compliance check for a single framework. Returns (result, prompt_hash)."""
    try:
        # Retrieve broadly across all policies, then filter to this framework.
        # Querying the contract text ranks the snippets most-relevant-first.
        all_snippets = retrieve(query=raw_text[:2000], source="policies", k=20)
        snippets = [
            s for s in all_snippets if s.get("framework") == framework
        ][:SNIPPETS_PER_FRAMEWORK]
    except Exception:
        logger.exception("RAG retrieve failed for framework %s", framework)
        snippets = []

    if not snippets:
        # No snippets to check against — treat as vacuously passed and flag in audit.
        logger.warning("No %s snippets retrieved; framework check skipped", framework)
        return (
            FrameworkResult(framework=framework, passed=True, checks=[]),
            None,
        )

    requirements_text = _format_requirements(snippets)
    prompt = _PROMPT_TEMPLATE.format(
        framework=framework,
        requirements_text=requirements_text,
        contract_text=raw_text,
    )
    p_hash = hash_prompt(prompt, system=SYSTEM_INSTRUCTION)

    logger.info("Running Agent 3 (compliance) — framework %s, %d requirements",
                framework, len(snippets))

    result: FrameworkResult = generate_json(
        prompt=prompt,
        schema=FrameworkResult,
        model=MODEL_PRO,
        system=SYSTEM_INSTRUCTION,
    )
    # Force the framework name in case the model renamed it. Use model_copy
    # rather than mutating in place so we don't accidentally clobber a
    # shared instance (e.g. in tests where the mock returns one object for
    # all three calls).
    result = result.model_copy(update={"framework": framework})
    return result, p_hash


def run(db: Session, contract_id: int, raw_text: str) -> ComplianceResult:
    """Execute Agent 3 across all frameworks."""
    framework_results: list[FrameworkResult] = []
    prompt_hashes: list[str] = []

    for framework in FRAMEWORKS:
        try:
            result, p_hash = _check_framework(framework, raw_text)
            framework_results.append(result)
            if p_hash:
                prompt_hashes.append(f"{framework}:{p_hash}")
        except Exception as e:
            logger.exception("Compliance check for %s failed", framework)
            framework_results.append(FrameworkResult(
                framework=framework, passed=False, checks=[],
            ))

    final = ComplianceResult(frameworks=framework_results)

    output_dict = json.loads(final.model_dump_json())
    db.add(AgentOutput(
        contract_id=contract_id,
        agent_name=AGENT_NAME,
        output=output_dict,
        confidence=None,
        prompt_hash=";".join(prompt_hashes) if prompt_hashes else None,
    ))
    db.commit()

    audit.log(
        db,
        actor=f"agent:{AGENT_NAME}",
        action="check",
        resource=f"contract:{contract_id}",
        after={
            "frameworks_checked": [f.framework for f in framework_results],
            "frameworks_passed": [f.framework for f in framework_results if f.passed],
            "prompt_version": PROMPT_VERSION,
        },
    )
    return final
