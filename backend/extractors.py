"""Text extraction from PDF and DOCX files.

Returns plaintext + a small metadata dict so downstream agents know
whether the document was OCR'd, how many pages, etc.
"""
import io
from pathlib import Path
from typing import Any

import pdfplumber
from docx import Document


def extract_text(file_bytes: bytes, filename: str) -> tuple[str, dict[str, Any]]:
    """Extract text from a PDF or DOCX file.

    Args:
        file_bytes: raw bytes of the uploaded file.
        filename: original filename, used to detect type via extension.

    Returns:
        (text, metadata)

    Raises:
        ValueError: unsupported file type.
    """
    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf":
        return _extract_pdf(file_bytes)
    if suffix == ".docx":
        return _extract_docx(file_bytes)
    raise ValueError(f"Unsupported file type: {suffix}")


def _extract_pdf(file_bytes: bytes) -> tuple[str, dict[str, Any]]:
    pages = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            pages.append(page.extract_text() or "")
    full_text = "\n\n".join(pages)
    return full_text, {
        "type": "pdf",
        "pages": len(pages),
        # If extracted text is suspiciously short, the PDF is likely scanned.
        "scanned": len(full_text.strip()) < 50 and len(pages) > 0,
    }


def _extract_docx(file_bytes: bytes) -> tuple[str, dict[str, Any]]:
    doc = Document(io.BytesIO(file_bytes))
    chunks = [p.text for p in doc.paragraphs if p.text.strip()]
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                if cell.text.strip():
                    chunks.append(cell.text)
    return "\n\n".join(chunks), {"type": "docx", "paragraphs": len(chunks)}
