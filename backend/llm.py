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

Retry logic: every API call is wrapped in `_call_with_retry`, which catches
429 RESOURCE_EXHAUSTED, parses the suggested retry delay out of the error
message, and sleeps + retries up to 3 times. This makes transient rate limits
invisible to callers.
"""
import hashlib
import os
from typing import Type, TypeVar

from dotenv import load_dotenv
from pydantic import BaseModel

from backend.gemini_client import call_with_retry, get_client

load_dotenv()

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

    result = call_with_retry(call)
    return result.text or ""


def generate_json(
    prompt: str,
    schema: Type[T],
    *,
    model: str = MODEL_FLASH,
    system: str | None = None,
    temperature: float = 0.1,
) -> T:
    """Generate structured output. Returns a parsed Pydantic instance."""
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

    result = call_with_retry(call)
    if getattr(result, "parsed", None) is not None:
        return result.parsed  # type: ignore[return-value]
    return schema.model_validate_json(result.text or "{}")
