"""Clause segmentation for contracts.

Splits raw text into structured clauses using common contract numbering patterns.
Falls back gracefully on documents without numbered headings.
"""
import re

# Match lines starting with patterns like "1.", "1.1", "1.2.3", "Section 4.2", "Article III".
# Title is captured as everything from the number to end of line.
CLAUSE_PATTERNS = [
    re.compile(
        r"^(?P<number>\d+(?:\.\d+)*)\.?\s+(?P<title>[A-Z][^\n]{2,100})",
        re.MULTILINE,
    ),
    re.compile(
        r"^Section\s+(?P<number>\d+(?:\.\d+)*)\s*[:.]?\s+(?P<title>[^\n]+)",
        re.MULTILINE | re.IGNORECASE,
    ),
    re.compile(
        r"^Article\s+(?P<number>[IVXLCDM]+|\d+)\s*[:.]?\s+(?P<title>[^\n]+)",
        re.MULTILINE | re.IGNORECASE,
    ),
]


def segment_clauses(text: str) -> list[dict]:
    """Split text into clauses. Each clause: {number, title, text}.

    If no numbered headings are detected, returns a single "0" clause
    containing the full text — downstream agents still work, they just
    can't cite by clause number.
    """
    matches = []
    for pattern in CLAUSE_PATTERNS:
        for m in pattern.finditer(text):
            matches.append((m.start(), m.end(), m.group("number"), m.group("title")))

    if not matches:
        return [{"number": "0", "title": "Body", "text": text.strip()}]

    # Sort by position, drop overlaps (keep earliest at each position).
    matches.sort(key=lambda x: x[0])
    deduped = []
    last_end = -1
    for start, end, number, title in matches:
        if start >= last_end:
            deduped.append((start, end, number, title))
            last_end = end

    clauses = []
    for i, (start, end, number, title) in enumerate(deduped):
        next_start = deduped[i + 1][0] if i + 1 < len(deduped) else len(text)
        body = text[end:next_start].strip()
        clauses.append({
            "number": number,
            "title": title.strip(),
            "text": body,
        })
    return clauses
