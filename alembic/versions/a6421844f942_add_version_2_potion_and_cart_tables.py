"""add version 2 potion and cart tables

Revision ID: a6421844f942
Revises: 3e0912bbe7fb
Create Date: 2026-04-13 19:11:30.569255

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a6421844f942"
down_revision: Union[str, None] = "3e0912bbe7fb"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "potions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("sku", sa.String, nullable=False, unique=True),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("quantity_on_hand", sa.Integer, nullable=False, server_default="0"),
        sa.Column("price", sa.Integer, nullable=False),
        sa.Column("red_ml", sa.Integer, nullable=False),
        sa.Column("green_ml", sa.Integer, nullable=False),
        sa.Column("blue_ml", sa.Integer, nullable=False),
        sa.Column("dark_ml", sa.Integer, nullable=False),
        sa.CheckConstraint(
            "red_ml + green_ml + blue_ml + dark_ml = 100", name="ml_sums_to_100"
        ),
    )
    op.create_table(
        "carts",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("customer_id", sa.String, nullable=False),
        sa.Column("customer_name", sa.String, nullable=False),
        sa.Column("character_class", sa.String, nullable=False),
        sa.Column("character_species", sa.String, nullable=False),
        sa.Column("character_level", sa.Integer, nullable=False),
    )
    op.create_table(
        "cart_items",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("cart_id", sa.Integer, sa.ForeignKey("carts.id"), nullable=False),
        sa.Column("potion_id", sa.Integer, sa.ForeignKey("potions.id"), nullable=False),
        sa.Column("quantity", sa.Integer, nullable=False, server_default="0"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("cart_items")
    op.drop_table("carts")
    op.drop_table("potions")
