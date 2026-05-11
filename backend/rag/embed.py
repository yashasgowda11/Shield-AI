"""Gemini embedding wrapper.

Uses `gemini-embedding-001` (3072 dim) via the maintained `google-genai` SDK.

Two task types matter for retrieval quality:
  - RETRIEVAL_DOCUMENT → for indexing
  - RETRIEVAL_QUERY    → for query-time embeddings

Loops single-content calls instead of using BatchEmbedContents. Why:
many free-tier and new-issue Gemini API keys block the batch endpoint
(`API_KEY_SERVICE_BLOCKED` 403). Single-content calls (`EmbedContent`)
are universally allowed. The corpus embedding loop runs once per cache
key, so this happens at most once per process startup.

Imports of `google.genai.types` are lazy so this module can be imported
in tests that never call the API. All API calls route through
`call_with_retry` so transient 429s are absorbed automatically.
"""
import numpy as np

from backend.gemini_client import call_with_retry, get_client

EMBEDDING_MODEL = "gemini-embedding-001"
EMBEDDING_DIM = 3072


def _embed_one(text: str, task_type: str) -> list[float]:
    from google.genai import types
    client = get_client()

    def call():
        return client.models.embed_content(
            model=EMBEDDING_MODEL,
            contents=text,  # single string → routes to EmbedContent, not BatchEmbedContents
            config=types.EmbedContentConfig(task_type=task_type),
        )

    result = call_with_retry(call)
    return result.embeddings[0].values


def embed_documents(texts: list[str]) -> np.ndarray:
    """Embed a list of documents for indexing. Returns shape (n, EMBEDDING_DIM).

    One API call per text. The corpus is small (~50 items) and gets cached to
    disk after first build, so this only runs once per cache key.
    """
    if not texts:
        return np.zeros((0, EMBEDDING_DIM), dtype=np.float32)
    out = [_embed_one(t, "RETRIEVAL_DOCUMENT") for t in texts]
    return np.array(out, dtype=np.float32)


def embed_query(text: str) -> np.ndarray:
    """Embed a single query. Returns shape (EMBEDDING_DIM,)."""
    return np.array(_embed_one(text, "RETRIEVAL_QUERY"), dtype=np.float32)


def embed_queries(texts: list[str]) -> np.ndarray:
    """Embed multiple queries. Returns shape (n, EMBEDDING_DIM).

    Loops single calls — N API round-trips, one per query. Originally batched,
    but BatchEmbedContents is blocked on many free-tier API keys.
    `call_with_retry` absorbs per-minute rate limits transparently.
    """
    if not texts:
        return np.zeros((0, EMBEDDING_DIM), dtype=np.float32)
    out = [_embed_one(t, "RETRIEVAL_QUERY") for t in texts]
    return np.array(out, dtype=np.float32)
