"""Shared frontend helpers: backend HTTP client and role-gating utilities.

Pages import via:
    import sys, pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
    from utils import api_get, api_post, current_role, can, gate
"""
import os
import streamlit as st
import httpx

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")


# ---- Backend HTTP client ----

def api_get(path: str, **kwargs):
    with httpx.Client(base_url=BACKEND_URL, timeout=30.0) as client:
        return client.get(path, **kwargs)


def api_post(path: str, **kwargs):
    with httpx.Client(base_url=BACKEND_URL, timeout=60.0) as client:
        return client.post(path, **kwargs)


def health_check() -> bool:
    try:
        r = api_get("/health")
        return r.status_code == 200
    except Exception:
        return False


# ---- Role-gating ----

PERMISSIONS = {
    "Procurement Analyst": {"upload", "view"},
    "Legal Reviewer": {"view", "approve_legal", "reject"},
    "Compliance Officer": {"view", "approve_manager", "reject"},
    "Executive": {"view"},
    "Auditor": {"view"},  # read-only across everything
}


def current_role() -> str:
    return st.session_state.get("role", "Procurement Analyst")


def can(action: str) -> bool:
    return action in PERMISSIONS.get(current_role(), set())


def gate(action: str, message: str | None = None) -> None:
    """Render a notice and stop the page if the role lacks permission."""
    if not can(action):
        st.warning(
            message
            or f"The **{current_role()}** role doesn't have permission for this action."
        )
        st.stop()
