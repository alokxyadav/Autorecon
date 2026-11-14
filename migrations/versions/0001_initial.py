"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-08-28

"""
from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "transactions",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("order_id", sa.String(), nullable=False, unique=True, index=True),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="INR"),
        sa.Column("status", sa.String(), nullable=False, server_default="captured"),
        sa.Column("source", sa.String(), nullable=False, server_default="razorpay_test_mode"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "settlements",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("razorpay_settlement_id", sa.String(), nullable=False, unique=True, index=True),
        sa.Column("transaction_order_id", sa.String(), nullable=False, index=True),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("fees", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("utr", sa.String(), nullable=False, index=True),
        sa.Column("settled_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "bank_statement_lines",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("description", sa.String(), nullable=False, server_default=""),
        sa.Column("utr_reference", sa.String(), nullable=True, index=True),
        sa.Column("value_date", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "reconciliation_results",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("transaction_id", sa.Integer(), sa.ForeignKey("transactions.id"), nullable=True, index=True),
        sa.Column("settlement_id", sa.Integer(), sa.ForeignKey("settlements.id"), nullable=True, index=True),
        sa.Column("bank_line_id", sa.Integer(), sa.ForeignKey("bank_statement_lines.id"), nullable=True, index=True),
        sa.Column("match_type", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, index=True),
        sa.Column("confidence", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("delta_amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("ai_proposed_resolution", sa.Text(), nullable=True),
        sa.Column("ai_confidence", sa.Integer(), nullable=True),
        sa.Column("reviewer_name", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("event_type", sa.String(), nullable=False, index=True),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("reasoning_text", sa.Text(), nullable=True),
        sa.Column("decided_by", sa.String(), nullable=False, server_default="system"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), index=True),
    )


def downgrade() -> None:
    op.drop_table("audit_log")
    op.drop_table("reconciliation_results")
    op.drop_table("bank_statement_lines")
    op.drop_table("settlements")
    op.drop_table("transactions")
