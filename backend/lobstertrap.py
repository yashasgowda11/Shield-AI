"""Adapter for Veea's Lobster Trap — deep prompt inspection proxy.

Repo: https://github.com/veeainc/lobstertrap

Lobster Trap is an OpenAI-compatible chat-completions proxy that runs DPI
on every prompt and returns a structured deny response when it catches
something. We send contract text through its inspection layer and parse
the verdict — we don't care about the backend hop (we point Lobster Trap
at a non-existent backend; only the DPI verdict matters).

Defaults match `./lobstertrap serve` out of the box (port 8080). Configure
via .env if you bind it elsewhere.
"""
import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)

URL = os.getenv("LOBSTERTRAP_URL", "http://localhost:8080")
TIMEOUT_SEC = float(os.getenv("LOBSTERTRAP_TIMEOUT_SEC", "5"))


def is_available() -> bool:
    """Probe the dashboard to see if Lobster Trap is reachable."""
    try:
        r = httpx.get(f"{URL}/_lobstertrap/", timeout=2.0)
        return r.status_code == 200
    except Exception:
        return False


def scan(text: str, agent_id: str = "shield-ai-security-gate") -> dict[str, Any] | None:
    """Send `text` to Lobster Trap for inspection.

    Returns:
        - dict with deny metadata if Lobster Trap blocked the request
        - None if the request was allowed, OR if Lobster Trap is unreachable
          (in which case the caller falls back to the offline detector)

    The returned dict (when present) has:
        verdict      : "DENY"
        rule_name    : Lobster Trap's rule that fired (e.g. "block_prompt_injection")
        deny_message : Human-readable block reason
        detected     : Full detection-flag bag from Lobster Trap
        risk_score   : Float 0-1 risk estimate
        request_id   : Lobster Trap's request id for cross-referencing the dashboard
    """
    try:
        resp = httpx.post(
            f"{URL}/v1/chat/completions",
            json={
                "model": "gpt-4o-mini",  # arbitrary — we never care about the model response
                "messages": [{"role": "user", "content": text}],
                "_lobstertrap": {
                    "agent_id": agent_id,
                    "declared_intent": "scan-contract-text",
                },
            },
            timeout=TIMEOUT_SEC,
        )
    except Exception as e:
        logger.warning(
            "Lobster Trap unreachable (%s); falling back to offline detector",
            type(e).__name__,
        )
        return None

    try:
        body = resp.json()
    except Exception:
        # If the backend hop failed and Lobster Trap couldn't synthesize a
        # response, the body may be malformed — treat as allowed.
        return None

    lt = body.get("_lobstertrap") or {}
    ingress = lt.get("ingress") or {}
    verdict = lt.get("verdict") or ingress.get("action")
    if verdict != "DENY":
        return None

    detected = ingress.get("detected") or {}
    deny_message = (
        body.get("choices", [{}])[0]
        .get("message", {})
        .get("content")
    )

    return {
        "verdict": "DENY",
        "rule_name": ingress.get("rule_name"),
        "deny_message": deny_message,
        "detected": detected,
        "risk_score": detected.get("risk_score"),
        "request_id": lt.get("request_id"),
    }
