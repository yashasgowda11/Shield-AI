"""SQLAlchemy models for the core tables.

Schema is intentionally minimal — each table has a clear, single purpose.
Adding columns later is cheap; adding tables is not.
"""
from datetime import datetime, timezone
from sqlalchemy import Boolean, Column, Integer, String, DateTime, JSON, Float, ForeignKey, Text
from sqlalchemy.orm import relationship
from backend.db import Base


def _utcnow() -> datetime:
    """Return current UTC time as a timezone-aware datetime.

    Replaces deprecated datetime.utcnow() throughout the models.
    SQLAlchemy stores it as UTC; consumers should treat all timestamps as UTC.
    """
    return datetime.now(timezone.utc)


class Contract(Base):
    __tablename__ = "contracts"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, nullable=False)
    status = Column(String, default="uploaded", index=True)
    # status values: uploaded | quarantined | processed | decided
    uploaded_at = Column(DateTime, default=_utcnow)
    raw_text = Column(Text)
    file_hash = Column(String, index=True)
    gcs_uri = Column(String)   # gs://bucket/contracts/<hash>.<ext>
    clauses = Column(JSON)  # list of {number, title, text, page}

    agent_outputs = relationship("AgentOutput", back_populates="contract")
    decisions = relationship("Decision", back_populates="contract")
    security_events = relationship("SecurityEvent", back_populates="contract")
    comments = relationship("ContractComment", back_populates="contract", order_by="ContractComment.created_at")
    assignments = relationship("ContractAssignment", back_populates="contract")


class AgentOutput(Base):
    """Every agent invocation writes a row here. The output JSON is the
    structured response from the agent; prompt_hash lets us detect drift.
    """
    __tablename__ = "agent_outputs"

    id = Column(Integer, primary_key=True)
    contract_id = Column(Integer, ForeignKey("contracts.id"), index=True)
    agent_name = Column(String, nullable=False, index=True)
    output = Column(JSON)
    confidence = Column(Float)
    prompt_hash = Column(String)
    created_at = Column(DateTime, default=_utcnow)

    contract = relationship("Contract", back_populates="agent_outputs")


class Decision(Base):
    """Records both AI recommendations (Agent 5) and human approvals."""
    __tablename__ = "decisions"

    id = Column(Integer, primary_key=True)
    contract_id = Column(Integer, ForeignKey("contracts.id"), index=True)
    recommendation = Column(String)
    # AUTO_APPROVE | MANAGER_REVIEW | LEGAL_REVIEW | REJECT
    reasoning = Column(Text)
    reviewer_role = Column(String)  # "agent:recommendation" or e.g. "Legal Reviewer"
    decided_at = Column(DateTime, default=_utcnow)
    # Rich scoring breakdown — populated by the hybrid scoring engine
    scoring_details = Column(JSON, nullable=True)

    contract = relationship("Contract", back_populates="decisions")


class SecurityEvent(Base):
    """Lobster Trap findings live here. event_type values:
    prompt_injection | data_exfiltration | suspicious_metadata | hallucination_flag
    """
    __tablename__ = "security_events"

    id = Column(Integer, primary_key=True)
    contract_id = Column(Integer, ForeignKey("contracts.id"), index=True)
    event_type = Column(String, index=True)
    severity = Column(String)  # low | medium | high | critical
    details = Column(JSON)
    created_at = Column(DateTime, default=_utcnow)

    contract = relationship("Contract", back_populates="security_events")


class ScoringPolicy(Base):
    """Stores the active (and historical) scoring policy configs.

    Admins edit the config via the Scoring Policy page — each save inserts a
    new row and deactivates the old one so the full history is preserved.
    """
    __tablename__ = "scoring_policies"

    id         = Column(Integer, primary_key=True)
    name       = Column(String, default="default", nullable=False)
    is_active  = Column(Boolean, default=True, nullable=False)
    config     = Column(JSON, nullable=False)   # full policy dict
    updated_by = Column(String, nullable=True)  # role/actor who saved it
    updated_at = Column(DateTime, default=_utcnow)


class ScoringFeedback(Base):
    """Human reviewer feedback on Agent 5's scoring decisions.

    Used as a reinforcement signal — drift patterns are surfaced in the
    Scoring Policy page so admins can tune weights and thresholds accordingly.
    """
    __tablename__ = "scoring_feedback"

    id              = Column(Integer, primary_key=True)
    contract_id     = Column(Integer, ForeignKey("contracts.id"), index=True)
    decision_id     = Column(Integer, ForeignKey("decisions.id"), index=True)
    # Score judgment from the reviewer
    feedback_type   = Column(String, nullable=False)  # too_high | too_low | correct
    # What the AI decided vs what the reviewer would have decided
    ai_decision     = Column(String)   # AUTO_APPROVE | MANAGER_REVIEW | LEGAL_REVIEW | REJECT
    human_decision  = Column(String)   # what the reviewer thinks it should have been
    composite_score = Column(Float)    # composite score at time of feedback
    notes           = Column(Text)     # optional free-text from reviewer
    reviewer_role   = Column(String)
    created_at      = Column(DateTime, default=_utcnow)


class ContractComment(Base):
    """A comment or recommendation left by any role on a contract.

    Executive and Auditor are read-only on decisions but can leave comments.
    Legal Reviewers and Compliance Officers can leave escalation notes.
    All comments are visible to every role that can view the contract.
    """
    __tablename__ = "contract_comments"

    id           = Column(Integer, primary_key=True)
    contract_id  = Column(Integer, ForeignKey("contracts.id"), index=True)
    actor        = Column(String, nullable=False)   # e.g. "user:Executive"
    role         = Column(String, nullable=False)   # e.g. "Executive"
    comment      = Column(Text, nullable=False)
    comment_type = Column(String, default="comment")
    # comment_type values:
    #   "comment"        — general observation
    #   "recommendation" — formal recommendation (Executive / Auditor advisory)
    #   "escalation"     — created when Legal/Compliance escalates to another role
    created_at   = Column(DateTime, default=_utcnow)

    contract = relationship("Contract", back_populates="comments")


class ContractAssignment(Base):
    """Tracks which roles are assigned to review a contract beyond the default queue.

    Created by:
      1. The orchestrator automatically when the AI recommendation warrants
         multi-role review (e.g. LEGAL_REVIEW + compliance failures → also
         assign Compliance Officer).
      2. Legal Reviewer / Compliance Officer manually escalating to another role.

    If can_approve=True the assigned role gains approve/reject permission for
    this specific contract, overriding their default read-only status.
    """
    __tablename__ = "contract_assignments"

    id            = Column(Integer, primary_key=True)
    contract_id   = Column(Integer, ForeignKey("contracts.id"), index=True)
    assigned_role = Column(String, nullable=False)   # role that receives the assignment
    assigned_by   = Column(String, nullable=False)   # actor who created the assignment
    can_approve   = Column(Boolean, default=False)   # True → assigned role can approve/reject
    note          = Column(Text)                     # reason for assignment
    active        = Column(Boolean, default=True)    # False after the role acts or revokes
    assigned_at   = Column(DateTime, default=_utcnow)

    contract = relationship("Contract", back_populates="assignments")


class AuditLog(Base):
    """Append-only. Every agent action and every human action lands here.
    Without this table, we don't have a governance story."""
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True)
    actor = Column(String, nullable=False, index=True)
    action = Column(String, nullable=False, index=True)
    resource = Column(String, index=True)
    before = Column(JSON)
    after = Column(JSON)
    timestamp = Column(DateTime, default=_utcnow, index=True)
