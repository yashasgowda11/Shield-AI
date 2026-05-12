"""initial_schema — create all Shield AI tables

Revision ID: 99733a20d3e2
Revises:
Create Date: 2026-05-11

Creates all 5 core tables from scratch:
  contracts, agent_outputs, decisions, security_events, audit_logs
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "99733a20d3e2"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "contracts",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("filename", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=True, index=True),
        sa.Column("uploaded_at", sa.DateTime(), nullable=True),
        sa.Column("raw_text", sa.Text(), nullable=True),
        sa.Column("file_hash", sa.String(), nullable=True, index=True),
        sa.Column("gcs_uri", sa.String(), nullable=True),
        sa.Column("clauses", sa.JSON(), nullable=True),
    )

    op.create_table(
        "agent_outputs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("contract_id", sa.Integer(), sa.ForeignKey("contracts.id"), index=True),
        sa.Column("agent_name", sa.String(), nullable=False, index=True),
        sa.Column("output", sa.JSON(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("prompt_hash", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )

    op.create_table(
        "decisions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("contract_id", sa.Integer(), sa.ForeignKey("contracts.id"), index=True),
        sa.Column("recommendation", sa.String(), nullable=True),
        sa.Column("reasoning", sa.Text(), nullable=True),
        sa.Column("reviewer_role", sa.String(), nullable=True),
        sa.Column("decided_at", sa.DateTime(), nullable=True),
    )

    op.create_table(
        "security_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("contract_id", sa.Integer(), sa.ForeignKey("contracts.id"), index=True),
        sa.Column("event_type", sa.String(), nullable=True, index=True),
        sa.Column("severity", sa.String(), nullable=True),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("actor", sa.String(), nullable=False, index=True),
        sa.Column("action", sa.String(), nullable=False, index=True),
        sa.Column("resource", sa.String(), nullable=True, index=True),
        sa.Column("before", sa.JSON(), nullable=True),
        sa.Column("after", sa.JSON(), nullable=True),
        sa.Column("timestamp", sa.DateTime(), nullable=True, index=True),
    )


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("security_events")
    op.drop_table("decisions")
    op.drop_table("agent_outputs")
    op.drop_table("contracts")
