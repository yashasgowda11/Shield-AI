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

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")


# ---- Backend HTTP client ----

def api_get(path: str, **kwargs):
    with httpx.Client(base_url=BACKEND_URL, timeout=30.0) as client:
        return client.get(path, **kwargs)


def api_post(path: str, **kwargs):
    with httpx.Client(base_url=BACKEND_URL, timeout=60.0) as client:
        return client.post(path, **kwargs)


def api_delete(path: str, **kwargs):
    with httpx.Client(base_url=BACKEND_URL, timeout=30.0) as client:
        return client.delete(path, **kwargs)


def health_check() -> bool:
    try:
        r = api_get("/health")
        return r.status_code == 200
    except Exception:
        return False


# ---- Role-gating ----

PERMISSIONS = {
    "Procurement Analyst": {"upload", "view", "delete"},
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
    key_suffix: str = "",
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
        # Fetch bytes server-side (Streamlit process → backend) then render
        # via streamlit-pdf-viewer (pdf.js under the hood).
        # This avoids the cross-origin iframe problem: st.components.v1.html
        # runs inside Streamlit's sandboxed iframe on port 8501, so a nested
        # iframe pointing to localhost:8000 is blocked by the browser.
        with st.spinner("Loading PDF preview…"):
            try:
                r = api_get(f"/contracts/{contract_id}/file")
            except Exception as exc:
                st.warning(f"Could not reach backend to load preview: {exc}")
                return

        if r.status_code != 200:
            st.warning(
                f"Preview unavailable (HTTP {r.status_code}). "
                "Download the file to view it."
            )
            return

        try:
            from streamlit_pdf_viewer import pdf_viewer
            pdf_viewer(
                input=r.content,
                width=700,
                height=height,
                key=f"pdf_preview_{contract_id}_{key_suffix}",
            )
        except Exception as exc:
            st.warning(f"PDF render failed: {exc}")

        st.download_button(
            label="⬇️  Download PDF",
            data=r.content,
            file_name=filename,
            mime="application/pdf",
            key=f"pdf_dl_{contract_id}_{key_suffix}",
        )

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
                    key=f"docx_dl_{contract_id}_{key_suffix}",
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
