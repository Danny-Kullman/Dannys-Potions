"""add amount sold to potions

Revision ID: b7d3f4a1c8e2
Revises: a6421844f942
Create Date: 2026-04-13 23:40:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b7d3f4a1c8e2"
down_revision: Union[str, None] = "a6421844f942"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "potions",
        sa.Column("amount_sold", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("potions", "amount_sold")
