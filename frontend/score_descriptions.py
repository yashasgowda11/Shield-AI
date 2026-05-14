"""Central definitions of every scoring parameter shown in the UI.

Import this in any page that displays scores so descriptions stay consistent.
Used as `help=` tooltip text in Streamlit widgets.
"""

# ── Per-agent score descriptions ──────────────────────────────────────────────

AGENT_SCORES = {
    "agent2_risk": {
        "label": "Agent 2 — Risk Score",
        "range": "0 – 100 (higher = riskier)",
        "description": (
            "Produced by Agent 2 (Risk Assessment) using Gemini. "
            "Gemini reads every clause plus similar clauses from past contracts stored in Pinecone. "
            "It rates each finding as Low / Medium / High / Critical, then assigns an overall score. "
            "0 means no material risks found. 100 means the contract is extremely risky."
        ),
        "threshold_hint": "≥70 historically triggers legal review in the old engine.",
    },
    "agent3_compliance": {
        "label": "Agent 3 — Compliance Average",
        "range": "0 – 100% (higher = more compliant)",
        "description": (
            "Produced by Agent 3 (Compliance Check) using Gemini. "
            "Checks the contract against HIPAA, SOC2, and GDPR requirements retrieved from your "
            "internal policy corpus in Pinecone. "
            "Critical gaps count 3× more than Medium gaps in the weighted average. "
            "100% means every applicable requirement is present and evidenced."
        ),
        "threshold_hint": "Below 40% can trigger legal review or rejection.",
    },
    "agent1_quality": {
        "label": "Agent 1 — Contract Quality",
        "range": "0 – 100% (higher = more complete)",
        "description": (
            "Produced by Agent 1 (Document Extraction) using Gemini Flash. "
            "Measures how complete the extracted fields are: parties (25 pts), governing law (20 pts), "
            "effective date (15 pts), contract term (15 pts), obligations (15 pts), payment terms (10 pts). "
            "A contract missing governing law or parties scores low here regardless of risk level."
        ),
        "threshold_hint": "Incomplete contracts are harder to assess accurately — this penalises them in the composite.",
    },
    "composite": {
        "label": "Composite Approval Score",
        "range": "0 – 100 (higher = better)",
        "description": (
            "The single score used by Agent 5 to route the contract. "
            "Formula: (100 − Agent2_risk) × risk_weight + compliance_avg × compliance_weight + quality × quality_weight. "
            "Default weights: Risk 50%, Compliance 35%, Quality 15%. "
            "Higher composite = healthier contract. "
            "Thresholds are configurable in the Scoring Policy page."
        ),
        "threshold_hint": "≥82 = Auto-Approve · 63–81 = Manager Review · 38–62 = Legal Review · <38 = Reject",
    },
}

# ── Finding severity descriptions ─────────────────────────────────────────────

SEVERITY = {
    "Critical": (
        "Deal-breaker — must be resolved before any approval. "
        "Even one Critical finding blocks auto-approval and usually triggers legal review or rejection."
    ),
    "High": (
        "Significant concern — usually requires negotiation. "
        "More than 2 High findings triggers legal review regardless of the composite score."
    ),
    "Medium": (
        "Should be reviewed by the requesting team. "
        "Does not automatically change the routing decision but contributes to the compliance average."
    ),
    "Low": (
        "Minor concern — acceptable without negotiation. "
        "Counts minimally in the compliance average weighting."
    ),
}

# ── Scoring policy parameter descriptions ─────────────────────────────────────

POLICY_PARAMS = {
    "weight_risk": (
        "How much Agent 2's risk assessment contributes to the composite score. "
        "Higher weight = riskier clauses have more impact on routing. "
        "Default: 50%."
    ),
    "weight_compliance": (
        "How much Agent 3's compliance average contributes to the composite score. "
        "Higher weight = missing HIPAA/GDPR/SOC2 requirements have more impact. "
        "Default: 35%."
    ),
    "weight_quality": (
        "How much Agent 1's extraction completeness contributes to the composite score. "
        "Higher weight = contracts with missing parties or dates are penalised more. "
        "Default: 15%."
    ),
    "composite_min_auto": (
        "Minimum composite score (0–100) for a contract to be auto-approved. "
        "Contracts at or above this threshold with no critical findings skip human review entirely."
    ),
    "composite_min_manager": (
        "Minimum composite score for manager-level review (Compliance Officer). "
        "Contracts between this and the auto-approve threshold go to the manager queue."
    ),
    "composite_min_legal": (
        "Minimum composite score for legal review. "
        "Contracts between this and the manager threshold go to the legal queue. "
        "Contracts below this threshold are rejected outright."
    ),
    "critical_max": (
        "Maximum number of Critical findings allowed before this band's conditions fail. "
        "0 means even one Critical finding disqualifies the contract from this routing level."
    ),
    "high_max": (
        "Maximum number of High findings allowed before this band's conditions fail. "
        "Exceeding this pushes the contract to the next stricter routing level."
    ),
    "framework_keywords": (
        "Case-insensitive substrings matched against Critical compliance check requirement names. "
        "If a Critical check with one of these keywords is missing, the contract is immediately rejected "
        "regardless of its composite score."
    ),
}

# ── Feedback / reinforcement descriptions ─────────────────────────────────────

FEEDBACK = {
    "too_high": (
        "The AI composite score is higher than it should be — "
        "the contract is actually riskier than the score suggests. "
        "Example: score was 78 (manager review) but you think it should have gone to legal review."
    ),
    "too_low": (
        "The AI composite score is lower than it should be — "
        "the contract is actually safer than the score suggests. "
        "Example: score was 55 (legal review) but you think it was fine for manager review."
    ),
    "correct": (
        "The AI score and routing decision were appropriate for this contract. "
        "Submitting this helps calibrate the reinforcement analysis."
    ),
}
