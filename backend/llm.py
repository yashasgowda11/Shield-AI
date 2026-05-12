"""Gemini text generation wrapper.

Two functions every agent uses:
  generate_text(prompt, ...)              → str
  generate_json(prompt, schema, ...)      → Pydantic instance

Models are configurable via env vars (defaults set for free-tier compatibility):
  GEMINI_MODEL_PRO   = gemini-2.5-flash-lite   (heavy reasoning — Risk, Compliance)
  GEMINI_MODEL_FLASH = gemini-2.5-flash-lite   (extraction, hallucination check)

Both default to flash-lite because:
  - gemini-2.5-pro       → free-tier limit is 0 RPD (paid only)
  - gemini-2.5-flash     → free-tier RPM is ~10, easy to hit during demos
  - gemini-2.5-flash-lite → free-tier RPM is ~30, RPD ~1500 (comfortable)

Override either via .env if you have a paid plan:
  GEMINI_MODEL_PRO=gemini-2.5-pro

Plus a stable hash helper that the agents stamp into agent_outputs.prompt_hash
so an audit reviewer can prove which prompt produced which decision.

Retry logic: every API call is wrapped in `call_with_retry`, which catches
429 RESOURCE_EXHAUSTED, parses the suggested retry delay out of the error
message, and sleeps + retries up to 3 times. This makes transient rate limits
invisible to callers.

Error handling:
  - Empty LLM response  → raises RuntimeError with model/schema context
  - Pydantic parse fail → raises ValueError with raw text snippet for debugging
  - API errors          → propagated as-is (caller decides retry strategy)
"""
import hashlib
import logging
import os
from typing import Type, TypeVar

from dotenv import load_dotenv
from pydantic import BaseModel, ValidationError

from backend.gemini_client import call_with_retry, get_client

load_dotenv()

logger = logging.getLogger(__name__)

MODEL_PRO = os.getenv("GEMINI_MODEL_PRO", "gemini-2.5-flash-lite")
MODEL_FLASH = os.getenv("GEMINI_MODEL_FLASH", "gemini-2.5-flash-lite")

T = TypeVar("T", bound=BaseModel)


def hash_prompt(prompt: str, system: str | None = None) -> str:
    """Stable short hash for audit trails. Includes system instruction if any."""
    payload = (system or "") + "\n---\n" + prompt
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def generate_text(
    prompt: str,
    *,
    model: str = MODEL_FLASH,
    system: str | None = None,
    temperature: float = 0.2,
) -> str:
    """Plain text generation."""
    from google.genai import types
    client = get_client()
    config_kwargs: dict = {"temperature": temperature}
    if system:
        config_kwargs["system_instruction"] = system

    def call():
        return client.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(**config_kwargs),
        )

    try:
        result = call_with_retry(call)
    except Exception as exc:
        logger.error("generate_text failed (model=%s): %s", model, exc)
        raise

    text = result.text or ""
    if not text.strip():
        logger.warning("generate_text returned empty response (model=%s)", model)
    return text


def generate_json(
    prompt: str,
    schema: Type[T],
    *,
    model: str = MODEL_FLASH,
    system: str | None = None,
    temperature: float = 0.1,
) -> T:
    """Generate structured output validated against a Pydantic schema.

    Raises:
        RuntimeError: LLM returned an empty response.
        ValueError:   LLM response could not be parsed into the schema.
        Exception:    Any API-level error from call_with_retry (rate limit,
                      network, etc.) — propagated unchanged so callers can
                      handle them explicitly.
    """
    from google.genai import types
    client = get_client()
    config_kwargs: dict = {
        "temperature": temperature,
        "response_mime_type": "application/json",
        "response_schema": schema,
    }
    if system:
        config_kwargs["system_instruction"] = system

    def call():
        return client.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(**config_kwargs),
        )

    # ---- API call ----
    try:
        result = call_with_retry(call)
    except Exception as exc:
        logger.error(
            "generate_json API call failed (model=%s schema=%s): %s",
            model, schema.__name__, exc,
        )
        raise

    # ---- SDK already parsed the response ----
    if getattr(result, "parsed", None) is not None:
        return result.parsed  # type: ignore[return-value]

    # ---- Fallback: parse raw JSON text ----
    raw = (result.text or "").strip()
    if not raw:
        raise RuntimeError(
            f"LLM returned an empty response "
            f"(model={model}, schema={schema.__name__})"
        )

    try:
        return schema.model_validate_json(raw)
    except ValidationError as exc:
        snippet = raw[:300] + ("…" if len(raw) > 300 else "")
        logger.error(
            "generate_json Pydantic validation failed (model=%s schema=%s).\n"
            "Raw response snippet: %s\nValidation errors: %s",
            model, schema.__name__, snippet, exc,
        )
        raise ValueError(
            f"LLM output could not be parsed into {schema.__name__}: {exc}"
        ) from exc
