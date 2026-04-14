"""add order history tables

Revision ID: c1f9a6d4e2b7
Revises: b7d3f4a1c8e2
Create Date: 2026-04-14 00:20:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c1f9a6d4e2b7"
down_revision: Union[str, None] = "b7d3f4a1c8e2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "order_history",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("customer_id", sa.String(), nullable=False),
        sa.Column("customer_name", sa.String(), nullable=False),
        sa.Column("character_class", sa.String(), nullable=False),
        sa.Column("character_species", sa.String(), nullable=False),
        sa.Column("character_level", sa.Integer(), nullable=False),
        sa.Column("total_potions_bought", sa.Integer(), nullable=False),
        sa.Column("total_gold_paid", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_table(
        "order_history_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("order_history.id"), nullable=False),
        sa.Column("potion_id", sa.Integer(), sa.ForeignKey("potions.id"), nullable=False),
        sa.Column("potion_sku", sa.String(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("unit_price", sa.Integer(), nullable=False),
        sa.Column("line_total", sa.Integer(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("order_history_items")
    op.drop_table("order_history")
