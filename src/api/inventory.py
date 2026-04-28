from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
import sqlalchemy
from src.api import auth
from src import database as db

router = APIRouter(
    prefix="/inventory",
    tags=["inventory"],
    dependencies=[Depends(auth.get_api_key)],
)


class InventoryAudit(BaseModel):
    number_of_potions: int
    ml_in_barrels: int
    gold: int


class CapacityPlan(BaseModel):
    potion_capacity: int = Field(
        ge=0, le=10, description="Potion capacity units, max 10"
    )
    ml_capacity: int = Field(ge=0, le=10, description="ML capacity units, max 10")


@router.get("/audit", response_model=InventoryAudit)
def get_inventory():
    """
    Returns an audit of the current inventory. Any discrepancies between
    what is reported here and my source of truth will be posted
    as errors on potion exchange.
    """

    with db.engine.begin() as connection:
        # Get gold from ledger (sum all gold ledger entries)
        gold_result = connection.execute(
            sqlalchemy.text(
                "SELECT COALESCE(SUM(change), 0) as gold FROM gold_ledger_entries"
            )
        ).one()
        gold = gold_result.gold

        # Get ml amounts from ledger (sum all ml ledger entries by color)
        ml_result = connection.execute(
            sqlalchemy.text(
                """SELECT 
                   COALESCE(SUM(CASE WHEN color = 'red' THEN change ELSE 0 END), 0) as red_ml,
                   COALESCE(SUM(CASE WHEN color = 'green' THEN change ELSE 0 END), 0) as green_ml,
                   COALESCE(SUM(CASE WHEN color = 'blue' THEN change ELSE 0 END), 0) as blue_ml,
                   COALESCE(SUM(CASE WHEN color = 'dark' THEN change ELSE 0 END), 0) as dark_ml
                FROM ml_ledger_entries"""
            )
        ).one()

        # Get total potions from potion ledger
        potions_result = connection.execute(
            sqlalchemy.text(
                "SELECT COALESCE(SUM(change), 0) as total_potions FROM potion_ledger_entries"
            )
        ).one()

        total_potions = potions_result.total_potions
        total_ml = (
            ml_result.red_ml
            + ml_result.green_ml
            + ml_result.blue_ml
            + ml_result.dark_ml
        )

    return InventoryAudit(
        number_of_potions=total_potions,
        ml_in_barrels=total_ml,
        gold=gold,
    )


@router.post("/plan", response_model=CapacityPlan)
def get_capacity_plan():
    """
    - Buy potion/ml capacity if utilization > 80%
    - Prioritize the more limiting resource first
    """
    with db.engine.begin() as connection:
        # Get gold from ledger
        gold_result = connection.execute(
            sqlalchemy.text(
                "SELECT COALESCE(SUM(change), 0) as gold FROM gold_ledger_entries"
            )
        ).one()
        gold = gold_result.gold

        # Get ml amounts from ledger
        ml_result = connection.execute(
            sqlalchemy.text(
                """SELECT 
                   COALESCE(SUM(CASE WHEN color = 'red' THEN change ELSE 0 END), 0) as red_ml,
                   COALESCE(SUM(CASE WHEN color = 'green' THEN change ELSE 0 END), 0) as green_ml,
                   COALESCE(SUM(CASE WHEN color = 'blue' THEN change ELSE 0 END), 0) as blue_ml,
                   COALESCE(SUM(CASE WHEN color = 'dark' THEN change ELSE 0 END), 0) as dark_ml
                FROM ml_ledger_entries"""
            )
        ).one()

        # Get potion count from ledger
        potions_result = connection.execute(
            sqlalchemy.text(
                "SELECT COALESCE(SUM(change), 0) as total_potions FROM potion_ledger_entries"
            )
        ).one()

        # Get capacity limits from global_inventory
        capacity_result = connection.execute(
            sqlalchemy.text(
                "SELECT max_potion_capacity, max_barrel_capacity FROM global_inventory"
            )
        ).one()

        total_ml = (
            ml_result.red_ml
            + ml_result.green_ml
            + ml_result.blue_ml
            + ml_result.dark_ml
        )
        total_potions = potions_result.total_potions
        max_potion_capacity = capacity_result.max_potion_capacity
        max_ml_capacity = capacity_result.max_barrel_capacity

        # Current capacity in units (1 unit = 50 potions or 10000 ml)
        current_potion_units = max_potion_capacity // 50
        current_ml_units = max_ml_capacity // 10000

        # Utilization percentages
        potion_utilization = (
            total_potions / max_potion_capacity if max_potion_capacity > 0 else 0
        )
        ml_utilization = total_ml / max_ml_capacity if max_ml_capacity > 0 else 0

        # Capacity purchases
        potion_capacity_purchase = 0
        ml_capacity_purchase = 0

        # Buy 1 unit if >80% utilized, up to 10 units total
        if potion_utilization > 0.8 and current_potion_units < 10 and gold >= 1000:
            potion_capacity_purchase = 1
            gold -= 1000

        if ml_utilization > 0.8 and current_ml_units < 10 and gold >= 1000:
            ml_capacity_purchase = 1
            gold -= 1000

    return CapacityPlan(
        potion_capacity=potion_capacity_purchase, ml_capacity=ml_capacity_purchase
    )


@router.post("/deliver/{order_id}", status_code=status.HTTP_204_NO_CONTENT)
def deliver_capacity_plan(capacity_purchase: CapacityPlan, order_id: int):
    """
    Processes the delivery of the planned capacity purchase. order_id is a
    unique value representing a single delivery; the call is idempotent.

    - Start with 1 capacity for 50 potions and 1 capacity for 10,000 ml of potion.
    - Each additional capacity unit costs 1000 gold.
    """
    total_cost = (
        capacity_purchase.potion_capacity + capacity_purchase.ml_capacity
    ) * 1000

    request_id = f"inventory_deliver_{order_id}"

    with db.engine.begin() as connection:
        # Check if this request has already been processed
        existing_request = connection.execute(
            sqlalchemy.text(
                "SELECT request_id FROM processed_requests WHERE request_id = :request_id"
            ),
            {"request_id": request_id},
        ).fetchone()

        if existing_request:
            # Already processed, return without doing anything
            return

        # Create a gold transaction for the capacity cost
        if total_cost > 0:
            gold_transaction = connection.execute(
                sqlalchemy.text(
                    """INSERT INTO gold_transactions (description) 
                       VALUES (:description) 
                       RETURNING id"""
                ),
                {"description": f"Bought capacity for {total_cost} gold"},
            ).one()
            gold_transaction_id = gold_transaction.id

            # Add gold ledger entry (negative because we're spending gold)
            connection.execute(
                sqlalchemy.text(
                    """INSERT INTO gold_ledger_entries (gold_transaction_id, change) 
                       VALUES (:transaction_id, :change)"""
                ),
                {"transaction_id": gold_transaction_id, "change": -total_cost},
            )

        # Update global_inventory to increase capacity
        connection.execute(
            sqlalchemy.text(
                """UPDATE global_inventory SET
                   max_potion_capacity = max_potion_capacity + :potion_capacity_increase,
                   max_barrel_capacity = max_barrel_capacity + :ml_capacity_increase
                """
            ),
            {
                "potion_capacity_increase": capacity_purchase.potion_capacity * 50,
                "ml_capacity_increase": capacity_purchase.ml_capacity * 10000,
            },
        )

        # Store the processed request
        connection.execute(
            sqlalchemy.text(
                """INSERT INTO processed_requests (request_id, response) 
                   VALUES (:request_id, :response)"""
            ),
            {"request_id": request_id, "response": sqlalchemy.JSON.cache_ok},
        )
