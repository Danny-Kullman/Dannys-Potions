"""Add Supabase metrics views

Revision ID: 9d3f1f5b2c10
Revises: f7a8b9c0d1e2
Create Date: 2026-05-11 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "9d3f1f5b2c10"
down_revision: Union[str, None] = "f7a8b9c0d1e2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "barrel_offers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("sku", sa.String(), nullable=False),
        sa.Column(
            "offered_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("ml_per_barrel", sa.Integer(), nullable=False),
        sa.Column("potion_type_red", sa.Numeric(), nullable=False),
        sa.Column("potion_type_green", sa.Numeric(), nullable=False),
        sa.Column("potion_type_blue", sa.Numeric(), nullable=False),
        sa.Column("potion_type_dark", sa.Numeric(), nullable=False),
        sa.Column("price", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"),
    )

    op.execute(
        sa.text(
            """
            CREATE OR REPLACE VIEW v_sales_per_potion_by_hour AS
            SELECT
                oh.hour_of_day,
                p.id AS potion_id,
                p.sku AS potion_sku,
                p.name AS potion_name,
                SUM(ohi.quantity) AS quantity_sold,
                SUM(ohi.line_total) AS gold_spent,
                COUNT(DISTINCT oh.id) AS order_count
            FROM order_history_items ohi
            JOIN order_history oh ON oh.id = ohi.order_id
            JOIN potions p ON p.id = ohi.potion_id
            GROUP BY oh.hour_of_day, p.id, p.sku, p.name
            ORDER BY p.sku, oh.hour_of_day;
            """
        )
    )

    op.execute(
        sa.text(
            """
            CREATE OR REPLACE VIEW v_barrel_offers AS
            SELECT
                id,
                sku,
                offered_at,
                ml_per_barrel,
                potion_type_red,
                potion_type_green,
                potion_type_blue,
                potion_type_dark,
                price,
                quantity,
                price::numeric / NULLIF(ml_per_barrel, 0) AS cost_per_ml,
                (potion_type_red + potion_type_green + potion_type_blue + potion_type_dark) AS composition_total
            FROM barrel_offers;
            """
        )
    )

    op.execute(
        sa.text(
            """
            CREATE OR REPLACE VIEW v_customer_potion_demand AS
            SELECT
                oh.character_class,
                oh.character_species,
                oh.character_level,
                CONCAT(oh.character_class, ' / ', oh.character_species, ' / L', oh.character_level) AS customer_segment,
                p.id AS potion_id,
                p.sku AS potion_sku,
                p.name AS potion_name,
                SUM(ohi.quantity) AS quantity_sold,
                SUM(ohi.line_total) AS gold_spent,
                COUNT(DISTINCT oh.id) AS order_count
            FROM order_history_items ohi
            JOIN order_history oh ON oh.id = ohi.order_id
            JOIN potions p ON p.id = ohi.potion_id
            GROUP BY oh.character_class, oh.character_species, oh.character_level, p.id, p.sku, p.name
            ORDER BY quantity_sold DESC, gold_spent DESC;
            """
        )
    )

    op.execute(
        sa.text(
            """
            CREATE OR REPLACE VIEW v_sales_by_hour_summary AS
            SELECT
                oh.hour_of_day,
                COUNT(DISTINCT oh.id) AS order_count,
                SUM(ohi.quantity) AS total_potions_sold,
                SUM(ohi.line_total) AS total_gold_spent,
                COUNT(DISTINCT p.id) AS unique_potions_sold
            FROM order_history_items ohi
            JOIN order_history oh ON oh.id = ohi.order_id
            JOIN potions p ON p.id = ohi.potion_id
            GROUP BY oh.hour_of_day
            ORDER BY oh.hour_of_day;
            """
        )
    )


def downgrade() -> None:
    op.execute(sa.text("DROP VIEW IF EXISTS v_sales_by_hour_summary"))
    op.execute(sa.text("DROP VIEW IF EXISTS v_customer_potion_demand"))
    op.execute(sa.text("DROP VIEW IF EXISTS v_barrel_offers"))
    op.execute(sa.text("DROP VIEW IF EXISTS v_sales_per_potion_by_hour"))
    op.drop_table("barrel_offers")
