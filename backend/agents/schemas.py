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
# Agent 0 — Contract Classifier
# ============================================================================

class ContractType(str, Enum):
    MSA        = "MSA"               # Master Services Agreement
    NDA        = "NDA"               # Non-Disclosure Agreement
    DPA        = "DPA"               # Data Processing Agreement (standalone)
    BAA        = "BAA"               # Business Associate Agreement (standalone)
    SAAS       = "SaaS"              # SaaS / Software Subscription Agreement
    EMPLOYMENT = "Employment"        # Employment / Contractor Agreement
    VENDOR     = "Vendor"            # Vendor / Supplier / Procurement Agreement
    LICENSE    = "License"           # IP / Software License Agreement
    PARTNER    = "Partnership"       # Joint Venture / Partnership Agreement
    SOW        = "SOW"               # Statement of Work (under an MSA)
    ADDENDUM   = "Addendum"          # Amendment or Addendum to existing agreement
    OTHER      = "Other"             # Does not fit any of the above


class Sector(str, Enum):
    HEALTHCARE    = "Healthcare"
    FINTECH       = "Fintech"
    TECHNOLOGY    = "Technology"
    GOVERNMENT    = "Government"
    EDUCATION     = "Education"
    ENERGY        = "Energy"
    REAL_ESTATE   = "RealEstate"
    LIFE_SCIENCES = "LifeSciences"
    RETAIL        = "Retail"
    DEFENSE       = "Defense"
    LEGAL         = "Legal"
    OTHER         = "Other"


class DataDomain(str, Enum):
    PHI         = "PHI"          # Protected Health Information (HIPAA)
    PII         = "PII"          # Personally Identifiable Information
    BIOMETRIC   = "Biometric"    # Fingerprints, face, iris, voice — triggers BIPA (IL)
    FINANCIAL   = "Financial"    # Payment cards, bank accounts, credit data
    STUDENT     = "StudentData"  # Education records — triggers FERPA
    GOVERNMENT  = "GovernmentData"  # CUI / FCI — triggers CMMC / FedRAMP
    NONE        = "None"         # No personal or regulated data involved


class ClassificationResult(BaseModel):
    """Output of Agent 0 — Contract Classifier."""

    # --- What kind of contract is this ---
    contract_type: ContractType = Field(
        description=(
            "Primary contract type. Choose the most specific type that fits. "
            "Use MSA for umbrella service agreements, NDA for confidentiality-only agreements, "
            "SaaS for cloud software subscriptions, DPA for standalone GDPR data processing agreements, "
            "BAA for standalone HIPAA business associate agreements."
        )
    )

    # --- What industry / sector does this serve ---
    sector: Sector = Field(
        description=(
            "The business sector this contract primarily serves. "
            "Healthcare = hospitals, clinics, health IT, insurers. "
            "Fintech = banking, payments, lending, insurance tech. "
            "Technology = SaaS, cloud, software, IT services (not healthcare-specific). "
            "Government = federal/state/local agencies, public sector. "
            "Defense = DoD contractors, defense supply chain. "
            "Education = universities, K-12, EdTech. "
            "Energy = oil/gas, utilities, renewables. "
            "LifeSciences = pharma, biotech, CROs, medical devices. "
            "Retail = ecommerce, consumer goods, distribution."
        )
    )

    # --- Geography ---
    jurisdiction_country: Optional[str] = Field(
        default=None,
        description=(
            "Primary governing country extracted from the contract text "
            "(e.g. 'United States', 'Germany', 'United Kingdom'). "
            "Null if not determinable."
        )
    )
    jurisdiction_us_state: Optional[str] = Field(
        default=None,
        description=(
            "US state if jurisdiction is within the United States "
            "(e.g. 'Delaware', 'California', 'New York'). "
            "Null if non-US or not stated."
        )
    )

    # --- What categories of regulated data are involved ---
    data_domains: list[DataDomain] = Field(
        description=(
            "All categories of regulated or sensitive data this contract involves. "
            "PHI = patient/medical records, HIPAA-covered data. "
            "PII = names, addresses, SSNs, any personal identifiers. "
            "Biometric = fingerprints, facial recognition, voice prints. "
            "Financial = payment cards, bank accounts, credit information. "
            "StudentData = student education records, grades, enrollment. "
            "GovernmentData = Controlled Unclassified Information, federal data. "
            "None = no personal or regulated data involved (e.g. pure IP license, NDA for trade secrets). "
            "Return [None] if no regulated data is involved."
        )
    )

    # --- Which compliance frameworks apply to this contract ---
    hipaa_applicable: bool = Field(
        description=(
            "True ONLY if this contract involves processing, storing, or transmitting "
            "Protected Health Information (PHI) or patient health records. "
            "False for general software licenses, NDAs, marketing services, and any "
            "contract that does not explicitly touch healthcare data."
        )
    )
    gdpr_applicable: bool = Field(
        description=(
            "True ONLY if this contract involves processing personal data of EU/EEA residents "
            "or the governing law / parties are based in the EU/EEA. "
            "False for US-only contracts with no EU data subjects."
        )
    )
    soc2_applicable: bool = Field(
        description=(
            "True if a vendor is providing cloud, SaaS, or managed services where they "
            "process, store, or transmit the customer's business data on their systems. "
            "False for pure goods procurement, NDAs, and one-time services with no data custody."
        )
    )
    pci_applicable: bool = Field(
        description=(
            "True ONLY if the contract involves processing, storing, or transmitting "
            "payment card data (credit/debit card numbers, CVV, expiry). "
            "False for all other contracts."
        )
    )
    ccpa_applicable: bool = Field(
        description=(
            "True if the contract involves processing personal data of California residents "
            "AND the business meets CCPA thresholds (annual revenue >$25M, or processes "
            "data of >100k California consumers, or derives >50% revenue from selling data). "
            "Also true if parties or operations are primarily in California."
        )
    )
    ferpa_applicable: bool = Field(
        description=(
            "True ONLY if the contract involves student education records, grades, "
            "enrollment data, or other data covered by the Family Educational Rights "
            "and Privacy Act. Sector must be Education."
        )
    )
    cmmc_applicable: bool = Field(
        description=(
            "True ONLY if the contract is with the US Department of Defense or a "
            "defense contractor, involving Federal Contract Information (FCI) or "
            "Controlled Unclassified Information (CUI)."
        )
    )

    # --- Reasoning and confidence ---
    classification_reasoning: str = Field(
        description=(
            "One to two sentences explaining why this contract type, sector, and "
            "framework selections were chosen. Cite specific contract text or party names."
        )
    )
    confidence: float = Field(
        ge=0.0, le=1.0,
        description=(
            "Confidence in this classification (0.0-1.0). "
            "Use 0.9+ when contract type is explicit (e.g. title says 'Master Services Agreement'). "
            "Use 0.7-0.89 when inferred from content. "
            "Use below 0.7 when ambiguous."
        )
    )


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


# ============================================================================
# Contract Q&A (Ask Shield AI — per-contract mode)
# ============================================================================

class ClauseCitation(BaseModel):
    number: str = Field(description="Clause number, e.g. '7.2'")
    title: str = Field(description="Clause title as it appears in the contract")
    relevance: str = Field(
        description="How relevant this clause is to the answer: high | medium | low",
    )


class ContractQAResult(BaseModel):
    """Output of the contract Q&A agent — grounded answer + clause citations."""
    answer: str = Field(description="Concise answer with §N.N inline citations")
    cited_clauses: list[ClauseCitation] = Field(
        description="Clauses that ground the answer, in order of relevance",
    )
    confidence: float = Field(
        ge=0.0, le=1.0,
        description="0-1 confidence the answer is correct and complete",
    )
