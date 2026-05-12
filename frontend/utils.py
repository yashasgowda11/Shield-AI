"""Shared frontend helpers: backend HTTP client and role-gating utilities.

Pages import via:
    import sys, pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
    from utils import api_get, api_post, current_role, can, gate, render_file_preview
"""
import os
from pathlib import Path

import httpx
import streamlit as st
import streamlit.components.v1 as components

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


# ---- File preview ----

def render_file_preview(
    contract_id: int,
    filename: str,
    raw_text: str | None = None,
    height: int = 700,
) -> None:
    """Render an inline file preview inside the calling page.

    PDF  → fetches bytes from GET /contracts/{id}/file, embeds in an iframe
           using a base64 data-URL so no GCS credentials are needed in the
           browser.
    DOCX → no browser-native viewer; falls back to the extracted raw text in
           a scrollable text area with a download button.

    Args:
        contract_id: DB id of the contract.
        filename:    Original filename (used to detect PDF vs DOCX).
        raw_text:    Pre-fetched extracted text (used for DOCX fallback).
        height:      Height of the PDF iframe in pixels (default 700).
    """
    suffix = Path(filename).suffix.lower()

    if suffix == ".pdf":
        # Point the iframe directly at the backend URL.
        # Chrome blocks data: URIs in iframes (CSP), but allows http(s):// URLs.
        file_url = f"{BACKEND_URL}/contracts/{contract_id}/file"
        pdf_html = f"""
        <iframe
            src="{file_url}"
            width="100%"
            height="{height}px"
            style="border:1px solid #e0e0e0; border-radius:6px;"
            type="application/pdf">
            <p style="padding:16px">
                Your browser cannot render this PDF inline.
                <a href="{file_url}" target="_blank">Open in new tab</a>
            </p>
        </iframe>
        """
        components.html(pdf_html, height=height + 20, scrolling=False)

        # Download button as a fallback / convenience
        try:
            r = api_get(f"/contracts/{contract_id}/file")
            if r.status_code == 200:
                st.download_button(
                    label="⬇️  Download PDF",
                    data=r.content,
                    file_name=filename,
                    mime="application/pdf",
                )
        except Exception:
            st.markdown(f"[⬇️ Download PDF]({file_url})")

    else:
        # DOCX — no browser-native viewer
        st.info(
            "📄 DOCX files cannot be rendered inline. "
            "Download the original or read the extracted text below."
        )
        try:
            r = api_get(f"/contracts/{contract_id}/file")
            if r.status_code == 200:
                st.download_button(
                    label="⬇️  Download DOCX",
                    data=r.content,
                    file_name=filename,
                    mime="application/vnd.openxmlformats-officedocument"
                         ".wordprocessingml.document",
                )
        except Exception:
            pass  # download button is optional — don't crash the page

        if raw_text:
            st.text_area(
                "Extracted text",
                value=raw_text,
                height=height,
                disabled=True,
                label_visibility="collapsed",
            )
