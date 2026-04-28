"""Implement ledger-based inventory and idempotency

Revision ID: f7a8b9c0d1e2
Revises: c1f9a6d4e2b7
Create Date: 2026-04-27 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f7a8b9c0d1e2"
down_revision: Union[str, None] = "c1f9a6d4e2b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create gold transaction table
    op.create_table(
        "gold_transactions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("description", sa.Text(), nullable=True),
    )

    # Create gold ledger entries table
    op.create_table(
        "gold_ledger_entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "gold_transaction_id",
            sa.Integer(),
            sa.ForeignKey("gold_transactions.id"),
            nullable=False,
        ),
        sa.Column("change", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    # Create ml transaction table
    op.create_table(
        "ml_transactions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("description", sa.Text(), nullable=True),
    )

    # Create ml ledger entries table with color tracking
    op.create_table(
        "ml_ledger_entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "ml_transaction_id",
            sa.Integer(),
            sa.ForeignKey("ml_transactions.id"),
            nullable=False,
        ),
        sa.Column(
            "color", sa.String(10), nullable=False
        ),  # 'red', 'green', 'blue', 'dark'
        sa.Column("change", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    # Create potion transaction table
    op.create_table(
        "potion_transactions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("description", sa.Text(), nullable=True),
    )

    # Create potion ledger entries table
    op.create_table(
        "potion_ledger_entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "potion_id",
            sa.Integer(),
            sa.ForeignKey("potions.id"),
            nullable=False,
        ),
        sa.Column(
            "potion_transaction_id",
            sa.Integer(),
            sa.ForeignKey("potion_transactions.id"),
            nullable=False,
        ),
        sa.Column("change", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    # Create processed_requests table for idempotency
    op.create_table(
        "processed_requests",
        sa.Column("request_id", sa.String(36), primary_key=True),
        sa.Column("response", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    # Add fields to order_history for tracking sale time and customer demographics
    op.add_column(
        "order_history",
        sa.Column(
            "hour_of_day",
            sa.Integer(),
            nullable=True,
            server_default=sa.text("EXTRACT(hour FROM now())"),
        ),
    )
    op.add_column(
        "order_history",
        sa.Column(
            "day_of_week",
            sa.Integer(),
            nullable=True,
            server_default=sa.text("EXTRACT(isodow FROM now())"),
        ),
    )

    # Create index on processed_requests for faster lookups
    op.create_index(
        "idx_processed_requests_request_id",
        "processed_requests",
        ["request_id"],
        unique=True,
    )


def downgrade() -> None:
    # Drop indices
    op.drop_index("idx_processed_requests_request_id", table_name="processed_requests")

    # Drop columns from order_history
    op.drop_column("order_history", "day_of_week")
    op.drop_column("order_history", "hour_of_day")

    # Drop ledger tables
    op.drop_table("processed_requests")
    op.drop_table("potion_ledger_entries")
    op.drop_table("potion_transactions")
    op.drop_table("ml_ledger_entries")
    op.drop_table("ml_transactions")
    op.drop_table("gold_ledger_entries")
    op.drop_table("gold_transactions")
