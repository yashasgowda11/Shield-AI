"""Shared Pydantic schemas for agent inputs/outputs.

These are passed to Gemini's structured-output mode (response_schema=).
Gemini converts them to JSON Schema, validates the model's response, and
returns a parsed instance.

Keep these stable across versions — every agent_outputs.output JSON we've
ever written assumes a specific shape.
"""
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ============================================================================
# Agent 1 — Document Extraction
# ============================================================================

class PartyRole(str, Enum):
    VENDOR = "Vendor"
    CUSTOMER = "Customer"
    LICENSOR = "Licensor"
    LICENSEE = "Licensee"
    DISCLOSER = "Discloser"
    RECIPIENT = "Recipient"
    BUYER = "Buyer"
    SELLER = "Seller"
    OTHER = "Other"


class Party(BaseModel):
    name: str = Field(description="Legal entity name as written in the contract")
    role: PartyRole = Field(description="Role in this agreement")


class Obligation(BaseModel):
    party: str = Field(description="Name of the party that owes the obligation")
    description: str = Field(description="What they're obligated to do")
    clause_ref: Optional[str] = Field(
        default=None,
        description="Clause number where the obligation appears, e.g. '7.2'",
    )


class ExtractionResult(BaseModel):
    """Output of Agent 1."""
    parties: list[Party] = Field(description="All parties to the agreement")
    effective_date: Optional[str] = Field(
        default=None,
        description="ISO date (YYYY-MM-DD) if explicitly stated, else null",
    )
    term: Optional[str] = Field(
        default=None,
        description="Human-readable term length, e.g. '2 years from Effective Date'",
    )
    payment_terms: Optional[str] = Field(
        default=None,
        description="e.g. 'Net 30', 'Net 60', or null if not applicable",
    )
    governing_law: Optional[str] = Field(
        default=None,
        description="Jurisdiction governing the contract, e.g. 'State of Delaware'",
    )
    obligations: list[Obligation] = Field(description="Material obligations of each party")
    summary: str = Field(description="Two to three sentences in plain English")


class Severity(str, Enum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    CRITICAL = "Critical"


class RiskFinding(BaseModel):
    risk: str = Field(description="Short label, e.g. 'Unlimited liability'")
    severity: Severity
    clause_ref: str = Field(description="Clause number this finding is grounded in")
    reasoning: str = Field(description="Why this is a risk, citing the clause text")


class RiskAssessment(BaseModel):
    """Output of Agent 2."""
    score: int = Field(ge=0, le=100, description="Aggregate risk score 0-100")
    findings: list[RiskFinding]


class ComplianceCheck(BaseModel):
    requirement: str
    present: bool
    evidence_quote: Optional[str] = Field(
        default=None,
        description="Quote from the contract showing presence (when present=True)",
    )
    gap_description: Optional[str] = Field(
        default=None,
        description="What's missing or insufficient (when present=False)",
    )
    severity: Severity = Field(default=Severity.MEDIUM)


class FrameworkResult(BaseModel):
    framework: str  # "HIPAA" | "SOC2" | "GDPR"
    passed: bool
    checks: list[ComplianceCheck]


class ComplianceResult(BaseModel):
    """Output of Agent 3."""
    frameworks: list[FrameworkResult]
