from fastapi import APIRouter, Depends, status
import sqlalchemy
from src.api import auth
from src import database as db

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(auth.get_api_key)],
)


@router.post("/reset", status_code=status.HTTP_204_NO_CONTENT)
def reset():
    """
    Reset the game state. Gold goes to 100, all potions are removed from
    inventory, and all barrels are removed from inventory. Carts are all reset.
    """

    with db.engine.begin() as connection:
        connection.execute(sqlalchemy.text("DELETE FROM cart_items"))
        connection.execute(sqlalchemy.text("DELETE FROM carts"))

        # Clear idempotency and historical order records.
        connection.execute(sqlalchemy.text("DELETE FROM processed_requests"))
        connection.execute(sqlalchemy.text("DELETE FROM order_history_items"))
        connection.execute(sqlalchemy.text("DELETE FROM order_history"))

        # Reset all potion counts in both legacy and ledger-based systems.
        connection.execute(sqlalchemy.text("DELETE FROM potion_ledger_entries"))
        connection.execute(sqlalchemy.text("DELETE FROM potion_transactions"))
        connection.execute(sqlalchemy.text("DELETE FROM potions"))
        connection.execute(sqlalchemy.text("UPDATE potions SET quantity_on_hand = 0"))

        # Reset all ML inventory movement in the ledger.
        connection.execute(sqlalchemy.text("DELETE FROM ml_ledger_entries"))
        connection.execute(sqlalchemy.text("DELETE FROM ml_transactions"))

        # Reset gold movement and seed starting balance in the ledger.
        connection.execute(sqlalchemy.text("DELETE FROM gold_ledger_entries"))
        connection.execute(sqlalchemy.text("DELETE FROM gold_transactions"))
        starting_gold_tx = connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO gold_transactions (description)
                VALUES ('Admin reset starting gold')
                RETURNING id
                """
            )
        ).one()
        connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO gold_ledger_entries (gold_transaction_id, change)
                VALUES (:transaction_id, 100)
                """
            ),
            {"transaction_id": starting_gold_tx.id},
        )

        # Keep legacy inventory columns in sync for backwards compatibility.
        connection.execute(
            sqlalchemy.text(
                """
                UPDATE global_inventory SET
                gold = 100,
                red_ml = 0,
                green_ml = 0,
                blue_ml = 0,
                dark_ml = 0
                """
            )
        )
