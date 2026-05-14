"""Deterministic scoring engine for Agent 5 — Recommendation.

NO LLM IS USED IN THIS MODULE. Every decision is rule-based and auditable.

Architecture
============
Upload → Lobster Trap + Offline Security Scan
       → Agent 0  (Classifier)  — contract type, sector, jurisdiction, data domains
       → Agent 1  (Extraction)  — parties, dates, term, governing law, obligations
       → Agent 2  (Risk)        — clause-level risk findings + aggregate score
       → Agent 3  (Compliance)  — framework checks (only applicable ones)
       → Agent 5  (THIS FILE)   — deterministic scoring + decision

Scoring layers (applied in order)
==================================
1. Security gate       — any Lobster Trap / offline event → immediate REJECT
2. Framework overrides — critical missing regulatory requirement → immediate REJECT
3. Sector policy       — weights and thresholds tuned per industry sector
4. Jurisdiction rules  — state-specific risk penalties (CA non-compete, TX indemnity…)
5. Financial risk      — liability cap, indemnification direction, insurance gaps
6. Composite formula   — (100−risk)×W_risk + compliance×W_compliance + quality×W_quality
7. Threshold bands     — AUTO_APPROVE / MANAGER_REVIEW / LEGAL_REVIEW / REJECT

Sector policies live in SECTOR_POLICIES below.
State rules live in STATE_RISK_RULES.
Financial rules live in FINANCIAL_RISK_RULES.
All are pure Python dicts — no DB required, no LLM required.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# ===========================================================================
# BASE POLICY
# Applies when no sector-specific policy matches or as the fallback.
# ===========================================================================

BASE_POLICY: dict[str, Any] = {
    "weights": {
        "risk":       0.50,
        "compliance": 0.35,
        "quality":    0.15,
    },
    "thresholds": {
        "auto_approve":   {"composite_min": 82, "critical_max": 0, "high_max": 1},
        "manager_review": {"composite_min": 63, "critical_max": 0, "high_max": 2},
        "legal_review":   {"composite_min": 38, "critical_max": 1, "high_max": 5},
    },
    "framework_rejection_rules": {
        "GDPR":  ["data processing agreement", "data breach notification", "subprocessor"],
        "HIPAA": ["business associate agreement", "breach notification", "phi safeguard"],
        "SOC2":  ["access control", "incident response", "security audit"],
    },
}

# Alias for backward compatibility with existing DB-loaded policies
DEFAULT_POLICY = BASE_POLICY


# ===========================================================================
# SECTOR POLICIES
#
# Each sector entry OVERRIDES specific fields in BASE_POLICY.
# Fields not listed here fall back to BASE_POLICY values.
#
# Rationale per sector is documented inline.
# ===========================================================================

SECTOR_POLICIES: dict[str, dict[str, Any]] = {

    # ── Healthcare ──────────────────────────────────────────────────────────
    # PHI exposure is catastrophic — HIPAA fines up to $1.9M per violation
    # category. Compliance is non-negotiable; risk weight slightly reduced
    # because a clean BAA + safeguards matters more than clause language risk.
    "Healthcare": {
        "weights": {
            "risk":       0.40,
            "compliance": 0.50,   # compliance dominates — PHI is life-safety
            "quality":    0.10,
        },
        "thresholds": {
            "auto_approve":   {"composite_min": 85, "critical_max": 0, "high_max": 0},
            "manager_review": {"composite_min": 68, "critical_max": 0, "high_max": 1},
            "legal_review":   {"composite_min": 40, "critical_max": 1, "high_max": 3},
        },
        "financial_penalty_triggers": {
            "phi_breach_not_carved_out":         15,  # composite deduction points
            "no_cyber_insurance_for_phi":        10,
            "uncapped_customer_indemnification": 20,
            "liability_cap_under_1x_fees":       10,
        },
        "sector_hard_reject_triggers": [
            # These RISK finding labels (from Agent 2) → immediate REJECT
            # regardless of composite score
            "uncapped customer indemnification",
        ],
    },

    # ── Fintech / Financial Services ────────────────────────────────────────
    # AML/KYC obligations, PCI DSS, GLBA, DORA (EU). Financial data breaches
    # carry regulatory fines + consumer class actions. Audit rights are
    # non-negotiable for financial regulators (OCC, FDIC, FCA).
    "Fintech": {
        "weights": {
            "risk":       0.45,
            "compliance": 0.45,
            "quality":    0.10,
        },
        "thresholds": {
            "auto_approve":   {"composite_min": 84, "critical_max": 0, "high_max": 1},
            "manager_review": {"composite_min": 65, "critical_max": 0, "high_max": 2},
            "legal_review":   {"composite_min": 38, "critical_max": 1, "high_max": 4},
        },
        "financial_penalty_triggers": {
            "uncapped_customer_indemnification": 20,
            "liability_cap_under_1x_fees":       15,  # stricter than base
            "no_audit_right":                    10,
            "payment_data_not_pci_scoped":       15,
        },
        "sector_hard_reject_triggers": [
            "uncapped customer indemnification",
            "extremely limited vendor liability",  # e.g. $1,000 cap
        ],
    },

    # ── Technology / SaaS ───────────────────────────────────────────────────
    # Default sector. SOC 2 is the de-facto standard. IP ownership and
    # data portability are key risk areas. Balanced weights.
    "Technology": {
        "weights": {
            "risk":       0.50,
            "compliance": 0.35,
            "quality":    0.15,
        },
        "thresholds": {
            "auto_approve":   {"composite_min": 82, "critical_max": 0, "high_max": 1},
            "manager_review": {"composite_min": 63, "critical_max": 0, "high_max": 2},
            "legal_review":   {"composite_min": 38, "critical_max": 1, "high_max": 5},
        },
        "financial_penalty_triggers": {
            "uncapped_customer_indemnification": 15,
            "liability_cap_under_2x_fees":       10,  # SaaS standard is 2× annual
            "broad_ip_assignment":               10,
        },
        "sector_hard_reject_triggers": [],
    },

    # ── Government / Public Sector ──────────────────────────────────────────
    # FAR/DFARS flow-downs, audit rights, and mandatory reporting requirements
    # dominate. Very high compliance bar. Auto-approve is rare.
    "Government": {
        "weights": {
            "risk":       0.30,
            "compliance": 0.60,   # government contracts are compliance-first
            "quality":    0.10,
        },
        "thresholds": {
            "auto_approve":   {"composite_min": 90, "critical_max": 0, "high_max": 0},
            "manager_review": {"composite_min": 72, "critical_max": 0, "high_max": 1},
            "legal_review":   {"composite_min": 45, "critical_max": 1, "high_max": 3},
        },
        "financial_penalty_triggers": {
            "no_audit_right":                    20,  # critical for government
            "uncapped_customer_indemnification": 15,
        },
        "sector_hard_reject_triggers": [
            "uncapped customer indemnification",
        ],
    },

    # ── Defense ─────────────────────────────────────────────────────────────
    # CMMC 2.0, ITAR, DFARS. Non-compliance can result in debarment.
    # Compliance weight is maximum; auto-approve virtually impossible
    # without verified CMMC certification and CUI protections.
    "Defense": {
        "weights": {
            "risk":       0.25,
            "compliance": 0.65,
            "quality":    0.10,
        },
        "thresholds": {
            "auto_approve":   {"composite_min": 92, "critical_max": 0, "high_max": 0},
            "manager_review": {"composite_min": 75, "critical_max": 0, "high_max": 1},
            "legal_review":   {"composite_min": 48, "critical_max": 1, "high_max": 2},
        },
        "financial_penalty_triggers": {
            "no_audit_right":                    25,
            "uncapped_customer_indemnification": 20,
        },
        "sector_hard_reject_triggers": [
            "uncapped customer indemnification",
        ],
    },

    # ── Education ───────────────────────────────────────────────────────────
    # FERPA, COPPA (if children under 13). Student data is sensitive.
    # Institutions are often budget-constrained — vendor liability caps
    # need to be proportional to contract value.
    "Education": {
        "weights": {
            "risk":       0.45,
            "compliance": 0.45,
            "quality":    0.10,
        },
        "thresholds": {
            "auto_approve":   {"composite_min": 82, "critical_max": 0, "high_max": 1},
            "manager_review": {"composite_min": 63, "critical_max": 0, "high_max": 2},
            "legal_review":   {"composite_min": 38, "critical_max": 1, "high_max": 4},
        },
        "financial_penalty_triggers": {
            "uncapped_customer_indemnification": 15,
            "liability_cap_under_1x_fees":        8,
            "student_data_retention_indefinite":  12,
        },
        "sector_hard_reject_triggers": [],
    },

    # ── Life Sciences / Pharma ──────────────────────────────────────────────
    # FDA regulations, GxP compliance, clinical trial data integrity (21 CFR
    # Part 11). IP ownership in research agreements is critical — who owns
    # the IP from a clinical trial can determine billion-dollar drug rights.
    "LifeSciences": {
        "weights": {
            "risk":       0.40,
            "compliance": 0.50,
            "quality":    0.10,
        },
        "thresholds": {
            "auto_approve":   {"composite_min": 86, "critical_max": 0, "high_max": 0},
            "manager_review": {"composite_min": 68, "critical_max": 0, "high_max": 1},
            "legal_review":   {"composite_min": 42, "critical_max": 1, "high_max": 3},
        },
        "financial_penalty_triggers": {
            "uncapped_customer_indemnification": 20,
            "broad_ip_assignment":               25,   # irrevocable IP loss in R&D
            "liability_cap_under_1x_fees":       12,
        },
        "sector_hard_reject_triggers": [
            "broad ip assignment",     # irrevocable IP assignment in LifeSciences = deal-breaker
            "uncapped customer indemnification",
        ],
    },

    # ── Energy / Utilities ──────────────────────────────────────────────────
    # NERC CIP for critical infrastructure. Force majeure is heavily
    # negotiated. Environmental liability can be uncapped by regulation.
    "Energy": {
        "weights": {
            "risk":       0.50,
            "compliance": 0.35,
            "quality":    0.15,
        },
        "thresholds": {
            "auto_approve":   {"composite_min": 82, "critical_max": 0, "high_max": 1},
            "manager_review": {"composite_min": 63, "critical_max": 0, "high_max": 2},
            "legal_review":   {"composite_min": 38, "critical_max": 1, "high_max": 5},
        },
        "financial_penalty_triggers": {
            "uncapped_customer_indemnification": 15,
            "environmental_liability_uncapped":  20,
        },
        "sector_hard_reject_triggers": [],
    },

    # ── Retail / eCommerce ──────────────────────────────────────────────────
    # PCI DSS for payments. Consumer protection laws (CCPA, state attorneys
    # general). Product liability if physical goods involved.
    "Retail": {
        "weights": {
            "risk":       0.50,
            "compliance": 0.35,
            "quality":    0.15,
        },
        "thresholds": {
            "auto_approve":   {"composite_min": 80, "critical_max": 0, "high_max": 1},
            "manager_review": {"composite_min": 60, "critical_max": 0, "high_max": 3},
            "legal_review":   {"composite_min": 35, "critical_max": 1, "high_max": 6},
        },
        "financial_penalty_triggers": {
            "uncapped_customer_indemnification": 12,
            "liability_cap_under_1x_fees":        8,
        },
        "sector_hard_reject_triggers": [],
    },

    # ── Real Estate / Construction ──────────────────────────────────────────
    # Anti-choice-of-law statutes (construction must use state where work
    # is performed). Retainage, lien rights, OSHA, and insurance minimums.
    "RealEstate": {
        "weights": {
            "risk":       0.55,   # operational risk dominates in construction
            "compliance": 0.30,
            "quality":    0.15,
        },
        "thresholds": {
            "auto_approve":   {"composite_min": 80, "critical_max": 0, "high_max": 2},
            "manager_review": {"composite_min": 60, "critical_max": 0, "high_max": 4},
            "legal_review":   {"composite_min": 35, "critical_max": 1, "high_max": 7},
        },
        "financial_penalty_triggers": {
            "uncapped_customer_indemnification": 12,
            "no_general_liability_insurance":    15,
        },
        "sector_hard_reject_triggers": [],
    },
}


# ===========================================================================
# STATE / JURISDICTION RISK RULES
#
# Applied when extracted governing_law matches a known state.
# Each rule specifies:
#   - match_keywords: substrings to find in governing_law string
#   - risk_flags: labels (lower-case) to look for in Agent 2 finding labels
#   - composite_deduction: points deducted from composite if triggered
#   - message: rationale text
# ===========================================================================

STATE_RISK_RULES: list[dict[str, Any]] = [
    {
        "state":          "California",
        "match_keywords": ["california", "state of california", "ca law"],
        "rules": [
            {
                "id":      "ca_noncompete_ban",
                "trigger_finding_labels": ["non-compete", "noncompete", "non compete"],
                "deduction": 20,
                "force_legal_review": True,
                "message": (
                    "California bans virtually all non-compete clauses (Bus. & Prof. Code §16600, "
                    "effective Jan 2024). Any non-compete in this contract is void and unenforceable "
                    "under CA law, and the employer may face civil liability. Legal review required."
                ),
                "action": (
                    "Remove non-compete clause — it is void under California law. "
                    "Consult legal counsel before enforcing any such clause against CA-based employees."
                ),
            },
            {
                "id":      "ca_ip_carveout",
                "trigger_finding_labels": ["broad ip assignment", "ip assignment", "intellectual property assignment"],
                "deduction": 10,
                "force_legal_review": False,
                "message": (
                    "California Labor Code §2870 protects employee IP developed on personal time "
                    "with personal resources. Overly broad IP assignment clauses may be partially "
                    "unenforceable in California."
                ),
                "action": (
                    "Verify IP assignment clause carves out inventions made entirely on employee's "
                    "own time without using company resources, consistent with CA Labor Code §2870."
                ),
            },
            {
                "id":      "ccpa_consumer_data",
                "trigger_finding_labels": ["personal data", "consumer data", "pii", "data sharing"],
                "deduction": 8,
                "force_legal_review": False,
                "message": (
                    "California CCPA/CPRA applies if this contract involves personal data of "
                    "California consumers. Verify data deletion rights and opt-out mechanisms."
                ),
                "action": "Confirm CCPA compliance obligations are addressed in the contract.",
            },
        ],
    },
    {
        "state":          "Illinois",
        "match_keywords": ["illinois", "state of illinois", "il law"],
        "rules": [
            {
                "id":      "il_bipa_biometric",
                "trigger_finding_labels": ["biometric", "facial recognition", "fingerprint", "voice print"],
                "deduction": 25,
                "force_legal_review": True,
                "message": (
                    "Illinois BIPA (Biometric Information Privacy Act) imposes strict requirements "
                    "on collection and use of biometric data, including written consent, retention "
                    "schedule, and prohibition on sale. Statutory damages: $1,000–$5,000 per violation."
                ),
                "action": (
                    "Legal review required. Contract must address BIPA consent, retention schedule, "
                    "and prohibition on monetization of biometric identifiers."
                ),
            },
            {
                "id":      "il_noncompete_wage",
                "trigger_finding_labels": ["non-compete", "noncompete"],
                "deduction": 10,
                "force_legal_review": False,
                "message": (
                    "Illinois prohibits non-compete agreements for employees earning below $75,000/year "
                    "(820 ILCS 90). Verify the contract party's compensation threshold."
                ),
                "action": "Confirm non-compete is limited to employees above the Illinois wage threshold.",
            },
        ],
    },
    {
        "state":          "Texas",
        "match_keywords": ["texas", "state of texas", "tx law"],
        "rules": [
            {
                "id":      "tx_express_negligence",
                "trigger_finding_labels": ["indemnif", "hold harmless"],
                "deduction": 8,
                "force_legal_review": False,
                "message": (
                    "Texas Express Negligence Doctrine: an indemnification clause that covers "
                    "a party's own negligence is unenforceable unless it EXPLICITLY states so "
                    "in clear and unambiguous language (Ethyl Corp. v. Daniel Constr. Co., 1987)."
                ),
                "action": (
                    "Verify indemnification clause explicitly states it covers indemnitee's own "
                    "negligence if that is the intent, or narrow the scope accordingly."
                ),
            },
            {
                "id":      "tx_limitations",
                "trigger_finding_labels": ["limitation", "limitation of liability", "liability cap"],
                "deduction": 5,
                "force_legal_review": False,
                "message": (
                    "Texas Civil Practice §16.070: contractual statute of limitations shorter "
                    "than 2 years is void."
                ),
                "action": "Verify no statute of limitations clause is shorter than 2 years.",
            },
        ],
    },
    {
        "state":          "New York",
        "match_keywords": ["new york", "state of new york", "ny law"],
        "rules": [
            {
                "id":      "ny_construction_law",
                "trigger_finding_labels": ["construction", "building", "contractor", "subcontractor"],
                "deduction": 8,
                "force_legal_review": False,
                "message": (
                    "New York anti-choice-of-law statute automatically voids out-of-state "
                    "governing law clauses in construction contracts performed in New York."
                ),
                "action": (
                    "Verify governing law clause is New York if construction work is performed in NY. "
                    "Out-of-state choice-of-law clauses are automatically void for NY construction."
                ),
            },
        ],
    },
    {
        "state":          "Delaware",
        "match_keywords": ["delaware", "state of delaware"],
        "rules": [
            # Delaware is business-friendly — no automatic penalties.
            # Courts enforce contracts as written. No deductions here,
            # but we note it for the rationale.
        ],
    },
    {
        "state":          "Maryland",
        "match_keywords": ["maryland", "state of maryland"],
        "rules": [
            {
                "id":      "md_noncompete_wage",
                "trigger_finding_labels": ["non-compete", "noncompete"],
                "deduction": 8,
                "force_legal_review": False,
                "message": (
                    "Maryland prohibits non-competes for employees earning ≤150% of state minimum wage. "
                    "Healthcare providers earning >$350k may have non-competes capped at 1 year "
                    "and 10-mile geographic restriction."
                ),
                "action": "Verify non-compete scope complies with Maryland wage threshold restrictions.",
            },
        ],
    },
]


# ===========================================================================
# FINANCIAL RISK RULES
#
# These fire when specific patterns are found in Agent 2's risk findings.
# The finding label matching is case-insensitive substring search.
# ===========================================================================

FINANCIAL_RISK_RULES: list[dict[str, Any]] = [
    {
        "id":                    "uncapped_customer_indemnification",
        "trigger_finding_labels": ["uncapped", "unlimited", "indemnif"],
        "trigger_finding_severity": ["Critical"],   # only fires on Critical findings
        "composite_deduction":   20,
        "force_legal_review":    True,
        "risk_category":         "Corporate Financial Risk",
        "message": (
            "Uncapped or unlimited customer indemnification exposes the company to "
            "unbounded financial liability. This is a critical corporate financial risk "
            "that requires legal negotiation before signing."
        ),
        "action": (
            "Negotiate a mutual indemnification clause with a cap tied to the contract value "
            "or a defined dollar amount. Never accept uncapped indemnification in vendor contracts."
        ),
    },
    {
        "id":                    "low_vendor_liability_cap",
        "trigger_finding_labels": ["limited vendor liability", "extremely limited", "liability cap"],
        "trigger_finding_severity": ["Critical", "High"],
        "composite_deduction":   15,
        "force_legal_review":    True,
        "risk_category":         "Corporate Financial Risk",
        "message": (
            "Vendor's liability cap is extremely low relative to the risk exposure. "
            "If the vendor causes a significant breach or failure, the company has "
            "virtually no meaningful financial recourse."
        ),
        "action": (
            "Negotiate vendor liability cap to at minimum 1× annual contract value, "
            "with a carve-out for data breaches (uncapped or super-cap)."
        ),
    },
    {
        "id":                    "asymmetric_termination",
        "trigger_finding_labels": ["asymmetric termination", "unilateral termination"],
        "trigger_finding_severity": ["Critical", "High"],
        "composite_deduction":   10,
        "force_legal_review":    False,
        "risk_category":         "Operational Risk",
        "message": (
            "Vendor can terminate the agreement unilaterally with minimal notice or "
            "for business reasons. This creates significant business continuity risk "
            "as services could be abruptly discontinued."
        ),
        "action": (
            "Negotiate mutual termination rights with at least 90 days notice "
            "and a cure period of 30 days for material breach."
        ),
    },
    {
        "id":                    "broad_ip_assignment",
        "trigger_finding_labels": ["broad ip assignment", "ip assignment", "irrevocable"],
        "trigger_finding_severity": ["Critical", "High"],
        "composite_deduction":   10,
        "force_legal_review":    False,
        "risk_category":         "Corporate IP Risk",
        "message": (
            "Overly broad IP assignment strips the company of ownership over innovations, "
            "insights, or derivative works created using the vendor's platform. "
            "This may include valuable business intelligence or proprietary algorithms."
        ),
        "action": (
            "Negotiate IP clause to limit assignment to vendor's pre-existing technology. "
            "Customer-generated insights and derivatives should remain customer property."
        ),
    },
    {
        "id":                    "data_sharing_third_party",
        "trigger_finding_labels": ["data sharing", "third-party", "third party", "monetization"],
        "trigger_finding_severity": ["Critical", "High"],
        "composite_deduction":   8,
        "force_legal_review":    False,
        "risk_category":         "Data Privacy Risk",
        "message": (
            "Contract permits vendor to share customer's usage data, query patterns, "
            "or business intelligence with third parties, including for monetization. "
            "This poses competitive and privacy risks."
        ),
        "action": (
            "Restrict data sharing to what is strictly necessary for service delivery. "
            "Explicitly prohibit sharing of business-sensitive data with competitors."
        ),
    },
    {
        "id":                    "post_termination_fees",
        "trigger_finding_labels": ["pay fees post-termination", "fees through", "fees after termination"],
        "trigger_finding_severity": ["Critical", "High"],
        "composite_deduction":   8,
        "force_legal_review":    False,
        "risk_category":         "Corporate Financial Risk",
        "message": (
            "Contract requires customer to pay fees through the end of the original term "
            "even after early termination. This creates a significant financial obligation "
            "for services that may no longer be received."
        ),
        "action": (
            "Negotiate termination for convenience clause that limits liability to "
            "fees for services actually received, plus reasonable wind-down costs."
        ),
    },
]


# ===========================================================================
# PERSONAL / CORPORATE RISK RULES
#
# Operational and lifecycle risks that affect the company's future
# business freedom.
# ===========================================================================

PERSONAL_CORPORATE_RISK_RULES: list[dict[str, Any]] = [
    {
        "id":                    "global_noncompete",
        "trigger_finding_labels": ["non-compete", "noncompete", "competing product"],
        "composite_deduction":   15,
        "force_legal_review":    True,
        "risk_category":         "Business Freedom Risk",
        "message": (
            "Broad non-compete clause restricts the company's ability to develop or "
            "market competing products globally for multiple years post-termination. "
            "This significantly limits future strategic options."
        ),
        "action": (
            "Negotiate non-compete to be narrowly scoped (specific geography, "
            "specific product category, max 1 year post-termination). "
            "Global and multi-year non-competes are generally unenforceable and harmful."
        ),
    },
    {
        "id":                    "non_solicitation",
        "trigger_finding_labels": ["non-solicitation", "nonsolicitation", "solicit"],
        "composite_deduction":   5,
        "force_legal_review":    False,
        "risk_category":         "HR Risk",
        "message": (
            "Non-solicitation clause restricts ability to hire vendor employees. "
            "Liquidated damages clauses for breach can be financially significant."
        ),
        "action": (
            "Verify non-solicitation scope is limited and liquidated damages are reasonable."
        ),
    },
    {
        "id":                    "data_retention_indefinite",
        "trigger_finding_labels": ["indefinitely", "retain", "data indefinitely"],
        "composite_deduction":   10,
        "force_legal_review":    False,
        "risk_category":         "Data Privacy Risk",
        "message": (
            "Vendor may retain customer data indefinitely after termination for its own "
            "business purposes. This contradicts GDPR deletion rights and creates "
            "long-term data privacy and competitive intelligence risks."
        ),
        "action": (
            "Require vendor to delete all customer data within 30 days of termination "
            "with written certification of deletion."
        ),
    },
    {
        "id":                    "unilateral_amendment",
        "trigger_finding_labels": ["unilateral amendment", "amend", "modify"],
        "composite_deduction":   8,
        "force_legal_review":    False,
        "risk_category":         "Contractual Risk",
        "message": (
            "Vendor can unilaterally amend contract terms (including pricing) by "
            "posting changes to their website or providing notice. "
            "Continued use constitutes acceptance, creating significant change risk."
        ),
        "action": (
            "Require mutual written amendment for any material change. "
            "Price changes should require 60+ days advance written notice."
        ),
    },
    {
        "id":                    "auto_renewal_short_notice",
        "trigger_finding_labels": ["automatically renew", "auto-renew", "auto renew"],
        "composite_deduction":   5,
        "force_legal_review":    False,
        "risk_category":         "Operational Risk",
        "message": (
            "Auto-renewal clause may lock the company into another contract term "
            "if notice deadline is missed. Short notice windows (< 60 days) "
            "are especially risky for large contracts."
        ),
        "action": (
            "Set a calendar reminder at least 90 days before contract expiry. "
            "Negotiate notice period to minimum 60–90 days."
        ),
    },
]


# ===========================================================================
# Output schema
# ===========================================================================

@dataclass
class ScoringResult:
    decision:          str    # AUTO_APPROVE | MANAGER_REVIEW | LEGAL_REVIEW | REJECT
    composite_score:   float  # 0-100, higher = better
    risk_score:        int    # raw Agent 2 score (0=safe, 100=risky)
    compliance_avg:    float  # weighted % of compliance checks passed
    quality_score:     float  # 0-100 contract completeness
    critical_findings: int
    high_findings:     int
    # New fields from enhanced scoring
    sector:            str    = "Other"
    jurisdiction:      str    = "Unknown"
    triggered_rules:   list[str] = field(default_factory=list)
    rationale:         list[str] = field(default_factory=list)
    required_actions:  list[str] = field(default_factory=list)
    # Penalty breakdown for transparency
    financial_penalties: list[str] = field(default_factory=list)
    jurisdiction_penalties: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "decision":              self.decision,
            "composite_score":       self.composite_score,
            "risk_score":            self.risk_score,
            "compliance_average":    self.compliance_avg,
            "quality_score":         self.quality_score,
            "critical_findings":     self.critical_findings,
            "high_findings":         self.high_findings,
            "sector":                self.sector,
            "jurisdiction":          self.jurisdiction,
            "triggered_rules":       self.triggered_rules,
            "rationale":             self.rationale,
            "required_actions":      self.required_actions,
            "financial_penalties":   self.financial_penalties,
            "jurisdiction_penalties": self.jurisdiction_penalties,
        }


# ===========================================================================
# Policy loader — DB first, then sector override, then base
# ===========================================================================

def load_policy(db: Session | None, sector: str | None = None) -> dict[str, Any]:
    """Return active scoring policy, optionally merged with sector overrides.

    Priority:
      1. DB-stored active policy (admin-configurable via UI)
      2. Sector-specific policy override merged on top of base
      3. BASE_POLICY fallback
    """
    base = BASE_POLICY.copy()

    # Try DB first
    if db is not None:
        try:
            from backend.models import ScoringPolicy
            row = (
                db.query(ScoringPolicy)
                .filter_by(is_active=True)
                .order_by(ScoringPolicy.updated_at.desc())
                .first()
            )
            if row and row.config:
                base = row.config
        except Exception:
            logger.exception("Could not load scoring policy from DB — using defaults")

    # Merge sector override on top
    if sector and sector in SECTOR_POLICIES:
        sector_overrides = SECTOR_POLICIES[sector]
        merged = {**base}
        # Only override keys that are present in the sector policy
        for key in ("weights", "thresholds"):
            if key in sector_overrides:
                merged[key] = sector_overrides[key]
        merged["_sector"] = sector
        merged["_sector_overrides_applied"] = list(sector_overrides.keys())
        return merged

    return base


# ===========================================================================
# Sub-score calculators (unchanged from original)
# ===========================================================================

_SEVERITY_WEIGHT = {"Critical": 3, "High": 2, "Medium": 1, "Low": 1}


def compute_compliance_average(compliance: dict | None) -> tuple[float, list[str]]:
    """Weighted compliance score (0-100) from Agent 3's output."""
    if not compliance:
        return 50.0, []

    total_w = passed_w = 0
    gaps: list[str] = []

    for fw in (compliance.get("frameworks") or []):
        fw_name = fw.get("framework", "?")
        for chk in (fw.get("checks") or []):
            w = _SEVERITY_WEIGHT.get(chk.get("severity", "Medium"), 1)
            total_w += w
            if chk.get("present"):
                passed_w += w
            else:
                gaps.append(
                    f"[{fw_name}] {chk.get('requirement', '?')} ({chk.get('severity', '?')})"
                )

    if total_w == 0:
        return 100.0, []

    return round((passed_w / total_w) * 100, 1), gaps


def compute_quality_score(extraction: dict | None) -> float:
    """Score 0-100 based on completeness of Agent 1's extraction."""
    if not extraction:
        return 50.0

    checks = [
        ("parties",       25, lambda v: isinstance(v, list) and len(v) >= 2),
        ("governing_law", 20, lambda v: bool(v)),
        ("effective_date", 15, lambda v: bool(v)),
        ("term",          15, lambda v: bool(v)),
        ("payment_terms", 10, lambda v: bool(v)),
        ("obligations",   15, lambda v: isinstance(v, list) and len(v) > 0),
    ]

    score = 0.0
    for key, points, test in checks:
        try:
            if test(extraction.get(key)):
                score += points
        except Exception:
            pass

    return min(score, 100.0)


def _compute_composite(
    risk_score: int,
    compliance_avg: float,
    quality_score: float,
    weights: dict,
) -> float:
    """Blend three sub-scores. Risk is inverted (higher raw = worse)."""
    inverted_risk = 100.0 - risk_score
    composite = (
        weights.get("risk",       0.50) * inverted_risk
        + weights.get("compliance", 0.35) * compliance_avg
        + weights.get("quality",    0.15) * quality_score
    )
    return round(composite, 1)


# ===========================================================================
# Framework override checker (critical missing regulatory requirements)
# ===========================================================================

def _check_framework_overrides(
    compliance: dict | None,
    rules: dict[str, list[str]],
) -> list[str]:
    """Return triggered override strings for critical missing requirements.

    Recomputes `passed` from actual checks — never trusts the stored field
    because the LLM historically set it incorrectly.
    """
    if not compliance:
        return []

    triggered: list[str] = []
    for fw in (compliance.get("frameworks") or []):
        checks = fw.get("checks") or []
        if not checks:
            continue  # no requirements → not applicable, skip
        if all(chk.get("present") for chk in checks):
            continue  # all passed
        fw_name = fw.get("framework", "")
        critical_keywords = rules.get(fw_name, [])
        for chk in checks:
            if chk.get("present"):
                continue
            if chk.get("severity") != "Critical":
                continue
            req_text = (chk.get("requirement") or "").lower()
            for keyword in critical_keywords:
                if keyword.lower() in req_text:
                    triggered.append(
                        f"{fw_name}_critical:{chk.get('requirement', keyword)}"
                    )
                    break

    return triggered


# ===========================================================================
# Jurisdiction risk checker
# ===========================================================================

def _check_jurisdiction_rules(
    findings: list[dict],
    governing_law: str | None,
) -> tuple[int, list[str], list[str], list[str]]:
    """Apply state-specific risk rules based on governing law and findings.

    Returns:
        (total_deduction, triggered_ids, rationale_lines, action_lines)
    """
    if not governing_law:
        return 0, [], [], []

    gl_lower = governing_law.lower()
    total_deduction = 0
    triggered_ids: list[str] = []
    rationale_lines: list[str] = []
    action_lines: list[str] = []
    force_legal_review_triggered = False

    finding_labels = [
        (f.get("risk") or "").lower()
        for f in findings
    ]

    for state_rule in STATE_RISK_RULES:
        # Check if governing law matches this state
        if not any(kw in gl_lower for kw in state_rule["match_keywords"]):
            continue

        for rule in state_rule.get("rules", []):
            # Check if any finding label matches the trigger labels
            trigger_labels = [t.lower() for t in rule["trigger_finding_labels"]]
            matched = any(
                any(tl in fl for tl in trigger_labels)
                for fl in finding_labels
            )
            if not matched:
                continue

            triggered_ids.append(f"jurisdiction:{rule['id']}")
            total_deduction += rule.get("deduction", 0)
            rationale_lines.append(f"[{state_rule['state']}] {rule['message']}")
            action_lines.append(rule.get("action", ""))
            if rule.get("force_legal_review"):
                force_legal_review_triggered = True

    return total_deduction, triggered_ids, rationale_lines, action_lines


# ===========================================================================
# Financial & corporate risk checker
# ===========================================================================

def _check_risk_signals(
    findings: list[dict],
    sector: str,
) -> tuple[int, list[str], list[str], list[str], list[str]]:
    """Scan Agent 2 findings for financial and corporate risk patterns.

    Returns:
        (total_deduction, triggered_ids, financial_penalties,
         rationale_lines, action_lines)
    """
    total_deduction = 0
    triggered_ids: list[str] = []
    fin_penalties: list[str] = []
    rationale_lines: list[str] = []
    action_lines: list[str] = []

    # Combine finding label + severity for matching
    finding_entries = [
        {
            "label":    (f.get("risk") or "").lower(),
            "severity": f.get("severity", "Low"),
        }
        for f in findings
    ]

    all_rules = FINANCIAL_RISK_RULES + PERSONAL_CORPORATE_RISK_RULES

    for rule in all_rules:
        trigger_labels   = [t.lower() for t in rule["trigger_finding_labels"]]
        trigger_severities = rule.get("trigger_finding_severity", None)  # None = any severity

        matched = False
        for entry in finding_entries:
            label_match = any(tl in entry["label"] for tl in trigger_labels)
            if not label_match:
                continue
            if trigger_severities and entry["severity"] not in trigger_severities:
                continue
            matched = True
            break

        if not matched:
            continue

        deduction = rule.get("composite_deduction", 0)

        # Check if sector policy has a higher penalty for this rule
        sector_policy = SECTOR_POLICIES.get(sector, {})
        sector_fin_penalties = sector_policy.get("financial_penalty_triggers", {})
        rule_id_short = rule["id"].replace("_", " ")
        for penalty_key, penalty_pts in sector_fin_penalties.items():
            if penalty_key.replace("_", " ") in rule_id_short or rule_id_short in penalty_key.replace("_", " "):
                deduction = max(deduction, penalty_pts)
                break

        triggered_ids.append(f"risk_signal:{rule['id']}")
        total_deduction += deduction
        fin_penalties.append(
            f"{rule.get('risk_category', 'Risk')}: {rule['id']} (−{deduction} pts)"
        )
        rationale_lines.append(rule["message"])
        action_lines.append(rule.get("action", ""))

    return total_deduction, triggered_ids, fin_penalties, rationale_lines, action_lines


# ===========================================================================
# Sector hard-reject checker
# ===========================================================================

def _check_sector_hard_rejects(
    findings: list[dict],
    sector: str,
) -> list[str]:
    """Check if any finding matches a sector-specific hard-reject trigger.

    Returns list of triggered rule IDs (non-empty = REJECT).
    """
    sector_policy = SECTOR_POLICIES.get(sector, {})
    hard_rejects = sector_policy.get("sector_hard_reject_triggers", [])
    if not hard_rejects:
        return []

    finding_labels = [(f.get("risk") or "").lower() for f in findings]
    triggered = []
    for trigger in hard_rejects:
        t_lower = trigger.lower()
        for label in finding_labels:
            if t_lower in label:
                triggered.append(f"sector_hard_reject:{trigger}")
                break

    return triggered


# ===========================================================================
# Main decision function
# ===========================================================================

def decide(
    risk:            dict | None,
    compliance:      dict | None,
    extraction:      dict | None,
    security_events: list[dict],
    policy:          dict,
    classification:  dict | None = None,
) -> ScoringResult:
    """Apply the full deterministic scoring algorithm. No LLM involved.

    Args:
        risk:            Agent 2 output dict (score + findings).
        compliance:      Agent 3 output dict (frameworks + checks).
        extraction:      Agent 1 output dict (parties, governing_law, etc.).
        security_events: Lobster Trap / offline security events.
        policy:          Active policy dict (from load_policy()).
        classification:  Agent 0 output dict (sector, jurisdiction, etc.).

    Returns:
        ScoringResult with decision, scores, rationale, and actions.
    """
    weights    = policy.get("weights",    BASE_POLICY["weights"])
    thresholds = policy.get("thresholds", BASE_POLICY["thresholds"])
    fw_rules   = policy.get("framework_rejection_rules",
                            BASE_POLICY["framework_rejection_rules"])

    # ── Extract context from classification ───────────────────────────────────
    sector        = (classification or {}).get("sector", "Other") or "Other"
    jurisdiction  = (
        (classification or {}).get("jurisdiction_us_state")
        or (classification or {}).get("jurisdiction_country")
        or (extraction or {}).get("governing_law")
        or "Unknown"
    )
    contract_type = (classification or {}).get("contract_type", "Other") or "Other"

    # ── Sub-scores ────────────────────────────────────────────────────────────
    agent_risk  = int((risk or {}).get("score") or 0)
    findings    = (risk or {}).get("findings") or []

    # Count Critical/High from Agent 2 risk findings
    critical_n  = sum(1 for f in findings if f.get("severity") == "Critical")
    high_n      = sum(1 for f in findings if f.get("severity") == "High")

    # Also count Critical/High from Agent 3 compliance failures
    for _fw in (compliance or {}).get("frameworks") or []:
        for _chk in (_fw.get("checks") or []):
            if not _chk.get("present"):
                _sev = _chk.get("severity", "")
                if _sev == "Critical":
                    critical_n += 1
                elif _sev == "High":
                    high_n += 1

    compliance_avg, gaps = compute_compliance_average(compliance)
    quality             = compute_quality_score(extraction)
    base_composite      = _compute_composite(agent_risk, compliance_avg, quality, weights)

    # ── Apply penalty deductions ──────────────────────────────────────────────
    governing_law_text = (extraction or {}).get("governing_law") or jurisdiction

    jur_deduction, jur_triggered, jur_rationale, jur_actions = _check_jurisdiction_rules(
        findings, governing_law_text
    )
    fin_deduction, fin_triggered, fin_penalties, fin_rationale, fin_actions = _check_risk_signals(
        findings, sector
    )

    total_deduction = jur_deduction + fin_deduction
    composite = max(0.0, round(base_composite - total_deduction, 1))

    if total_deduction > 0:
        logger.info(
            "Scoring: base_composite=%.1f  jurisdiction_deduction=%d  "
            "financial_deduction=%d  final_composite=%.1f",
            base_composite, jur_deduction, fin_deduction, composite,
        )

    # Build result lists
    triggered: list[str] = []
    rationale: list[str] = []
    actions:   list[str] = []
    fin_penalty_log: list[str] = fin_penalties
    jur_penalty_log: list[str] = []

    if jur_triggered:
        triggered.extend(jur_triggered)
        rationale.extend(jur_rationale)
        actions.extend(a for a in jur_actions if a)
        jur_penalty_log = [
            f"[{jurisdiction}] {r[:80]}…" if len(r) > 80 else f"[{jurisdiction}] {r}"
            for r in jur_rationale
        ]
    if fin_triggered:
        triggered.extend(fin_triggered)
        rationale.extend(fin_rationale)
        actions.extend(a for a in fin_actions if a)

    def _build(decision: str) -> ScoringResult:
        return ScoringResult(
            decision=decision,
            composite_score=composite,
            risk_score=agent_risk,
            compliance_avg=compliance_avg,
            quality_score=quality,
            critical_findings=critical_n,
            high_findings=high_n,
            sector=sector,
            jurisdiction=jurisdiction,
            triggered_rules=triggered,
            rationale=rationale,
            required_actions=actions,
            financial_penalties=fin_penalty_log,
            jurisdiction_penalties=jur_penalty_log,
        )

    # ── Step 1: Security gate → REJECT ────────────────────────────────────────
    if security_events:
        types = ", ".join(sorted({e.get("event_type", "unknown") for e in security_events}))
        triggered.append("security_events_present")
        rationale.append(
            f"{len(security_events)} security event(s) flagged during upload scan "
            f"({types}). Contract cannot proceed."
        )
        actions.append("Investigate all security events and resubmit a clean document.")
        return _build("REJECT")

    # ── Step 2: Framework overrides → REJECT ─────────────────────────────────
    fw_overrides = _check_framework_overrides(compliance, fw_rules)
    if fw_overrides:
        triggered.extend(fw_overrides)
        for rule in fw_overrides:
            fw_name, _, req = rule.partition("_critical:")
            rationale.append(
                f"Critical {fw_name} requirement absent: '{req}'. "
                "This is a non-negotiable compliance control."
            )
            actions.append(f"Vendor must provide {req} before contract can proceed.")
        return _build("REJECT")

    # ── Step 3: Sector hard rejects → REJECT ─────────────────────────────────
    sector_rejects = _check_sector_hard_rejects(findings, sector)
    if sector_rejects:
        triggered.extend(sector_rejects)
        rationale.append(
            f"Contract contains a clause that is a hard-reject for the {sector} sector: "
            f"{', '.join(sector_rejects)}."
        )
        actions.append(
            f"This clause type is non-negotiable in {sector} contracts. "
            "Remove or replace before proceeding."
        )
        return _build("REJECT")

    # ── Step 4: Jurisdiction force-legal-review check ─────────────────────────
    for jur_rule_id in jur_triggered:
        rule_id_clean = jur_rule_id.replace("jurisdiction:", "")
        for state_rule in STATE_RISK_RULES:
            for rule in state_rule.get("rules", []):
                if rule["id"] == rule_id_clean and rule.get("force_legal_review"):
                    triggered.append("jurisdiction_force_legal_review")
                    rationale.append(
                        f"State-specific rule ({rule['id']}) mandates legal review "
                        f"for contracts under {state_rule['state']} law."
                    )

    # ── Step 5: Financial risk force-legal-review check ───────────────────────
    for fin_rule_id in fin_triggered:
        rule_id_clean = fin_rule_id.replace("risk_signal:", "")
        for rule in FINANCIAL_RISK_RULES + PERSONAL_CORPORATE_RISK_RULES:
            if rule["id"] == rule_id_clean and rule.get("force_legal_review"):
                triggered.append("financial_risk_force_legal_review")

    # ── Step 6: Threshold bands ───────────────────────────────────────────────
    auto_t  = thresholds.get("auto_approve",   BASE_POLICY["thresholds"]["auto_approve"])
    mgr_t   = thresholds.get("manager_review", BASE_POLICY["thresholds"]["manager_review"])
    legal_t = thresholds.get("legal_review",   BASE_POLICY["thresholds"]["legal_review"])

    force_legal = (
        "jurisdiction_force_legal_review" in triggered
        or "financial_risk_force_legal_review" in triggered
    )

    # AUTO_APPROVE — only if no force-legal and thresholds met
    if (
        not force_legal
        and composite    >= auto_t.get("composite_min", 82)
        and critical_n   <= auto_t.get("critical_max", 0)
        and high_n       <= auto_t.get("high_max", 1)
    ):
        rationale.append(
            f"Composite score {composite}/100 meets the auto-approval threshold "
            f"(≥{auto_t['composite_min']}) for the {sector} sector. "
            f"Risk score {agent_risk}/100, compliance average {compliance_avg:.0f}%, "
            f"no critical findings."
        )
        return _build("AUTO_APPROVE")

    # MANAGER_REVIEW
    if (
        not force_legal
        and composite    >= mgr_t.get("composite_min", 63)
        and critical_n   <= mgr_t.get("critical_max", 0)
        and high_n       <= mgr_t.get("high_max", 2)
    ):
        rationale.append(
            f"Composite score {composite}/100 falls in the manager-review band "
            f"({mgr_t['composite_min']}–{auto_t['composite_min'] - 1}) "
            f"for the {sector} sector. Minor to moderate issues — manager sign-off required."
        )
        if gaps:
            rationale.append(f"Open compliance gaps: {'; '.join(gaps[:3])}.")
            actions.append("Manager should verify compliance gaps before signing.")
        if high_n:
            actions.append(f"Review {high_n} high-severity finding(s) with the requesting team.")
        return _build("MANAGER_REVIEW")

    # LEGAL_REVIEW
    if (
        force_legal
        or composite    >= legal_t.get("composite_min", 38)
        or high_n       >= 3
        or critical_n   >= 1
    ):
        if high_n >= 3:
            triggered.append("multiple_high_severity_findings")
            rationale.append(f"{high_n} high-severity findings require legal scrutiny.")
            actions.append("Legal team must review and negotiate all high-severity clauses.")
        if critical_n >= 1:
            triggered.append("critical_finding_present")
            rationale.append(f"{critical_n} critical finding(s) detected — legal review mandatory.")
            actions.append("Resolve all critical findings before any approval.")
        if composite < auto_t.get("composite_min", 82):
            rationale.append(
                f"Composite score {composite}/100 is below the auto-approval threshold "
                f"for the {sector} sector. Significant risk or compliance gaps require legal assessment."
            )
        if gaps:
            actions.append(f"Address compliance gaps: {'; '.join(gaps[:4])}.")
        if total_deduction > 0:
            rationale.append(
                f"Score reduced by {total_deduction} points due to jurisdiction/financial "
                f"risk rules (base score was {base_composite}/100)."
            )
        return _build("LEGAL_REVIEW")

    # REJECT — below all thresholds
    triggered.append("composite_below_minimum_threshold")
    rationale.append(
        f"Composite score {composite}/100 is below the minimum acceptable level "
        f"({legal_t['composite_min']}) for the {sector} sector. Contract poses unacceptable risk."
    )
    if critical_n:
        triggered.append("critical_findings_exceed_limit")
        rationale.append(f"{critical_n} critical finding(s) present.")
        actions.append("All critical findings must be resolved before resubmission.")
    if gaps:
        actions.append(f"Critical compliance gaps must be remediated: {'; '.join(gaps)}.")

    return _build("REJECT")
