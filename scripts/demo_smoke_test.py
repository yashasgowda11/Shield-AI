"""Demo regression test — uploads each demo contract and asserts the
pipeline lands on an expected status. Catches drift after prompt changes.

Run: make demo-test  (backend must be running on port 8000).
Exits non-zero on any failure.
"""
import sys
import time
from pathlib import Path

import httpx

BACKEND_URL = "http://127.0.0.1:8000"
DEMO_DIR = Path(__file__).resolve().parents[1] / "demo_contracts"


# Each entry: file → expected outcomes.
#   "final_status" can be a string or list of acceptable strings.
EXPECTATIONS: dict[str, dict] = {
    "Clean_NDA.pdf": {
        # Mutual NDA — minimal risk
        "final_status": ["approved"],
        "must_run": ["extraction", "risk", "compliance", "recommendation"],
    },
    "SaaS_Standard.pdf": {
        # Clean SaaS with SOC 2 + GDPR DPA — should auto-approve
        "final_status": ["approved"],
        "must_run": ["extraction", "risk", "compliance", "recommendation"],
    },
    "Standard_Procurement.pdf": {
        # Either is acceptable depending on Gemini's risk score this run
        "final_status": ["approved", "manager_review"],
        "must_run": ["extraction", "risk", "compliance", "recommendation"],
    },
    "Vendor_Moderate.pdf": {
        # Designed for MANAGER_REVIEW — moderate risk, no Critical gaps
        "final_status": ["manager_review", "approved"],  # Gemini variability
        "must_run": ["extraction", "risk", "compliance", "recommendation"],
    },
    "Risky_Vendor.pdf": {
        # Designed for MANAGER_REVIEW / LEGAL_REVIEW — elevated risk
        "final_status": ["manager_review", "legal_review"],
        "must_run": ["extraction", "risk", "compliance", "recommendation"],
    },
    "Healthcare_NoBAA.pdf": {
        # Designed for LEGAL_REVIEW — Critical HIPAA compliance gap
        # (processes PHI but missing BAA)
        "final_status": ["legal_review", "manager_review"],
        "must_run": ["extraction", "risk", "compliance", "recommendation"],
    },
    "Vendor_Agreement.pdf": {
        # Quarantined by the security gate before agents run
        "final_status": ["quarantined"],
        "must_run": [],
    },
}


def upload(filename: str) -> dict:
    path = DEMO_DIR / filename
    if not path.exists():
        return {"error": f"file not found: {path}"}
    with path.open("rb") as f:
        r = httpx.post(
            f"{BACKEND_URL}/contracts/upload",
            files={"file": (filename, f.read(), "application/pdf")},
            timeout=180.0,
        )
    if r.status_code != 200:
        return {"error": f"HTTP {r.status_code}: {r.text[:200]}"}
    return r.json()


def main() -> None:
    # Each non-quarantined upload makes ~10 Gemini calls (extraction + 5 risk
    # retrievals + 1 risk generation + 1 compliance retrieval + 3 compliance
    # generations). On free-tier flash-lite (~30 RPM) that's right at the cap.
    # Sleeping between uploads avoids hitting the per-minute limit.
    UPLOAD_SPACING_SEC = 30

    failures = 0
    for i, (filename, exp) in enumerate(EXPECTATIONS.items()):
        if i > 0:
            print(f"\n   …waiting {UPLOAD_SPACING_SEC}s to avoid rate limit…")
            time.sleep(UPLOAD_SPACING_SEC)
        print(f"\n→ {filename}")
        result = upload(filename)
        if "error" in result:
            print(f"   ✗ {result['error']}")
            failures += 1
            continue

        status = result.get("status")
        ok_status = status in exp["final_status"]
        ran = (result.get("pipeline") or {}).get("ran") or []
        ok_ran = all(a in ran for a in exp["must_run"])

        status_marker = "✓" if ok_status else "✗"
        print(
            f"   {status_marker} status: {status}   (expected one of {exp['final_status']})"
        )
        if exp["must_run"]:
            ran_marker = "✓" if ok_ran else "✗"
            print(f"   {ran_marker} ran:    {ran}")
        if not ok_status or not ok_ran:
            failures += 1

    print()
    if failures:
        print(f"FAIL — {failures} demo(s) did not behave as expected.")
        sys.exit(1)
    print("PASS — all demo contracts behaved as expected.")


if __name__ == "__main__":
    main()
