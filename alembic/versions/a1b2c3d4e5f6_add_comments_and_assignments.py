"""Add contract_comments and contract_assignments tables

Revision ID: a1b2c3d4e5f6
Revises: 99733a20d3e2
Create Date: 2026-05-13

Enables:
  - Any role to leave comments / recommendations on a contract
  - Legal / Compliance to escalate contracts to other roles with optional approve permission
  - Orchestrator to auto-assign multi-role review when AI recommendation warrants it
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "99733a20d3e2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "contract_comments",
        sa.Column("id",           sa.Integer(),  primary_key=True),
        sa.Column("contract_id",  sa.Integer(),  sa.ForeignKey("contracts.id"), nullable=False, index=True),
        sa.Column("actor",        sa.String(),   nullable=False),
        sa.Column("role",         sa.String(),   nullable=False),
        sa.Column("comment",      sa.Text(),     nullable=False),
        sa.Column("comment_type", sa.String(),   nullable=False, server_default="comment"),
        sa.Column("created_at",   sa.DateTime(), nullable=False, server_default=sa.text("NOW()")),
    )

    op.create_table(
        "contract_assignments",
        sa.Column("id",            sa.Integer(),  primary_key=True),
        sa.Column("contract_id",   sa.Integer(),  sa.ForeignKey("contracts.id"), nullable=False, index=True),
        sa.Column("assigned_role", sa.String(),   nullable=False),
        sa.Column("assigned_by",   sa.String(),   nullable=False),
        sa.Column("can_approve",   sa.Boolean(),  nullable=False, server_default="false"),
        sa.Column("note",          sa.Text()),
        sa.Column("active",        sa.Boolean(),  nullable=False, server_default="true"),
        sa.Column("assigned_at",   sa.DateTime(), nullable=False, server_default=sa.text("NOW()")),
    )


def downgrade() -> None:
    op.drop_table("contract_assignments")
    op.drop_table("contract_comments")
