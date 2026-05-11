"""Agent 4 — Security Governance.

Pre-LLM security gate. Runs on extracted text BEFORE any Gemini call.

Two-layer defense:
  1. Veea's Lobster Trap (deep prompt inspection proxy) — primary.
     Sends extracted text through Lobster Trap's /v1/chat/completions
     and parses any DENY verdict. Repo: https://github.com/veeainc/lobstertrap
  2. Offline pattern detector — complement and fallback. Catches the
     same families plus zero-width unicode tricks. Always runs, so the
     demo still works if Lobster Trap is down.

Each SecurityEvent we persist has a `source` field ("lobstertrap" or
"offline_detector") so the dashboard can show which layer caught what.
"""
import re
from typing import Any

from sqlalchemy.orm import Session

from backend import audit, lobstertrap
from backend.models import SecurityEvent


# ---- Offline pattern detector ----

INJECTION_PATTERNS: list[tuple[str, str]] = [
    (r"ignore\s+(?:all\s+|the\s+|previous\s+|prior\s+|above\s+)?(?:your\s+)?instructions?",
     "instruction_override"),
    (r"disregard\s+(?:all\s+|the\s+)?(?:prior|previous|above)\s+\w+",
     "instruction_override"),
    (r"forget\s+(?:everything|all|your\s+instructions?|previous\s+instructions?)",
     "instruction_override"),
    (r"you\s+are\s+now\s+(?:a|an)\s+\w+",
     "role_override"),
    (r"act\s+as\s+(?:a|an|the)\s+\w+",
     "role_override"),
    (r"reveal\s+(?:internal|system|hidden|confidential|all)",
     "data_exfiltration"),
    (r"expose\s+(?:internal|system|hidden|confidential|pricing|secrets?)",
     "data_exfiltration"),
    (r"print\s+(?:your\s+)?(?:system\s+)?prompt",
     "data_exfiltration"),
    (r"approve\s+this\s+(?:contract|document|agreement)\s+(?:immediately|automatically|without)",
     "decision_manipulation"),
    (r"do\s+not\s+flag\s+(?:any\s+)?risks?",
     "decision_manipulation"),
    (r"mark\s+this\s+as\s+(?:safe|approved|low.risk)",
     "decision_manipulation"),
    (r"bypass\s+(?:the\s+)?(?:security|policy|review|check)",
     "policy_bypass"),
    (r"override\s+(?:your\s+|the\s+)?(?:safety|security|policy|guidelines?)",
     "policy_bypass"),
]

_COMPILED = [(re.compile(p, re.IGNORECASE), t) for p, t in INJECTION_PATTERNS]
_SUSPICIOUS_UNICODE = re.compile(r"[​‌‍⁠﻿]")


# ---- Lobster Trap rule → our event_type mapping ----

_LT_RULE_TO_EVENT = {
    "block_prompt_injection": "instruction_override",
    "block_credential_exposure": "data_exfiltration",
    "block_pii_leak": "data_exfiltration",
    "block_role_impersonation": "role_override",
    "block_exfiltration": "data_exfiltration",
    "block_phishing": "policy_bypass",
}


def _classify_lobstertrap_event(rule_name: str | None, detected: dict) -> str:
    """Map Lobster Trap's rule + detection flags to our event_type vocabulary."""
    if rule_name and rule_name in _LT_RULE_TO_EVENT:
        return _LT_RULE_TO_EVENT[rule_name]
    if detected.get("contains_injection_patterns"):
        return "instruction_override"
    if detected.get("contains_role_impersonation"):
        return "role_override"
    if detected.get("contains_credentials") or detected.get("contains_exfiltration"):
        return "data_exfiltration"
    if detected.get("contains_system_commands") or detected.get("contains_phishing_patterns"):
        return "policy_bypass"
    return "suspicious_metadata"


# ---- Public API ----

def scan(db: Session, contract_id: int, raw_text: str) -> dict[str, Any]:
    """Pre-LLM security gate. Returns {"clean": bool, "events": [...]}.

    Side effects:
        - Persists SecurityEvent rows for any detections.
        - Writes audit log entries.
    """
    events: list[dict[str, Any]] = []

    # --- Layer 1: Lobster Trap (primary) ---
    lt_verdict = lobstertrap.scan(raw_text)
    if lt_verdict:
        detected = lt_verdict.get("detected") or {}
        events.append({
            "event_type": _classify_lobstertrap_event(
                lt_verdict.get("rule_name"), detected,
            ),
            "severity": "critical",
            "details": {
                "source": "lobstertrap",
                "rule_name": lt_verdict.get("rule_name"),
                "deny_message": lt_verdict.get("deny_message"),
                "matched_text": lt_verdict.get("deny_message"),
                "risk_score": lt_verdict.get("risk_score"),
                "request_id": lt_verdict.get("request_id"),
                "detected_flags": [
                    k for k, v in detected.items()
                    if isinstance(v, bool) and v
                ],
                "confidence": 0.95,
            },
        })

    # --- Layer 2: Offline pattern detector (always runs) ---
    for pattern, event_type in _COMPILED:
        for match in pattern.finditer(raw_text):
            window_start = max(0, match.start() - 40)
            window_end = min(len(raw_text), match.end() + 40)
            events.append({
                "event_type": event_type,
                "severity": "critical",
                "details": {
                    "source": "offline_detector",
                    "matched_text": match.group(0),
                    "context": raw_text[window_start:window_end].strip(),
                    "char_offset": match.start(),
                    "confidence": 0.95,
                },
            })

    # Zero-width / invisible characters
    zwc_matches = _SUSPICIOUS_UNICODE.findall(raw_text)
    if zwc_matches:
        events.append({
            "event_type": "suspicious_metadata",
            "severity": "high",
            "details": {
                "source": "offline_detector",
                "character_count": len(zwc_matches),
                "description": (
                    f"{len(zwc_matches)} zero-width or invisible character(s) detected. "
                    "Common technique for hiding instructions inside seemingly normal text."
                ),
                "confidence": 0.99,
            },
        })

    # --- Persist + audit ---
    for ev in events:
        db.add(SecurityEvent(
            contract_id=contract_id,
            event_type=ev["event_type"],
            severity=ev["severity"],
            details=ev["details"],
        ))
        audit.log(
            db,
            actor="agent:security",
            action="detect",
            resource=f"contract:{contract_id}",
            after=ev,
        )
    if events:
        db.commit()

    return {"clean": not events, "events": events}
