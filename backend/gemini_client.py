"""Singleton client for the google-genai SDK.

Both the embedding wrapper (rag/embed.py) and the generation wrapper (llm.py)
import from here so they share one client + one source of error messages.

Also exposes `call_with_retry` — a thin wrapper around any genai API call that
catches 429 RESOURCE_EXHAUSTED, parses the suggested retry delay out of the
error message, and sleeps + retries up to N times. Both embeddings and
generations route through this so per-minute rate limits become invisible.

Lazy-init pattern: importing this module is free; first call to get_client()
validates the API key and instantiates the SDK.
"""
import logging
import os
import re
import time
from typing import Callable

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

_client = None


def get_client():
    """Return the singleton genai.Client. Raises clearly if not configured."""
    global _client
    if _client is not None:
        return _client

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key or api_key.startswith("your_"):
        raise RuntimeError(
            "GEMINI_API_KEY not set in .env. "
            "Get a key at https://aistudio.google.com/apikey"
        )
    try:
        from google import genai
    except ImportError as e:
        raise RuntimeError(
            "google-genai not installed. Run: pip install google-genai"
        ) from e

    _client = genai.Client(api_key=api_key)
    return _client


def reset_client() -> None:
    """For tests that need to swap clients. Don't call in production code."""
    global _client
    _client = None


def call_with_retry(fn: Callable, max_attempts: int = 3, base_delay: float = 2.0):
    """Run an API call, retrying on 429 with the server-suggested delay.

    The Gemini error message contains "Please retry in Xs" — we parse it and
    sleep that long. Falls back to exponential backoff if no hint is present.
    Daily-cap exhaustion (which would also be 429) blows past max_attempts
    and surfaces as the original exception.
    """
    for attempt in range(max_attempts):
        try:
            return fn()
        except Exception as e:
            msg = str(e)
            is_rate_limit = "429" in msg or "RESOURCE_EXHAUSTED" in msg
            if not is_rate_limit or attempt == max_attempts - 1:
                raise
            match = re.search(r"retry in (\d+(?:\.\d+)?)s", msg)
            delay = float(match.group(1)) if match else base_delay * (2 ** attempt)
            delay = min(delay + 0.5, 60.0)  # cap at 60s, add 500ms buffer
            logger.warning(
                "Rate-limited (attempt %d/%d). Sleeping %.1fs before retry.",
                attempt + 1, max_attempts, delay,
            )
            time.sleep(delay)
    raise RuntimeError("retry loop exited without returning")
