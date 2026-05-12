"""SQLAlchemy models for the 5 core tables.

Schema is intentionally minimal — five tables cover the entire data model.
Adding columns later is cheap; adding tables is not.
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, JSON, Float, ForeignKey, Text
from sqlalchemy.orm import relationship
from backend.db import Base


class Contract(Base):
    __tablename__ = "contracts"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, nullable=False)
    status = Column(String, default="uploaded", index=True)
    # status values: uploaded | quarantined | processed | decided
    uploaded_at = Column(DateTime, default=datetime.utcnow)
    raw_text = Column(Text)
    file_hash = Column(String, index=True)
    gcs_uri = Column(String)   # gs://bucket/contracts/<hash>.<ext>
    clauses = Column(JSON)  # list of {number, title, text, page}

    agent_outputs = relationship("AgentOutput", back_populates="contract")
    decisions = relationship("Decision", back_populates="contract")
    security_events = relationship("SecurityEvent", back_populates="contract")


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
    created_at = Column(DateTime, default=datetime.utcnow)

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
    decided_at = Column(DateTime, default=datetime.utcnow)

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
    created_at = Column(DateTime, default=datetime.utcnow)

    contract = relationship("Contract", back_populates="security_events")


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
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
