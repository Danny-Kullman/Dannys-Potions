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
        # Get ml from global_inventory
        inventory = connection.execute(
            sqlalchemy.text(
                """SELECT gold, red_ml, green_ml, blue_ml, dark_ml
                FROM global_inventory"""
            )
        ).one()

        # Get total potions from potions table
        potions = connection.execute(
            sqlalchemy.text("SELECT COALESCE(SUM(quantity_on_hand), 0) FROM potions")
        ).one()

        gold = inventory.gold
        total_potions = potions[0]
        total_ml = (
            inventory.red_ml
            + inventory.green_ml
            + inventory.blue_ml
            + inventory.dark_ml
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
        inventory = connection.execute(
            sqlalchemy.text(
                """SELECT gold, red_ml, green_ml, blue_ml, dark_ml,
                          max_potion_capacity, max_barrel_capacity
                   FROM global_inventory"""
            )
        ).one()

        potions_result = connection.execute(
            sqlalchemy.text("SELECT COALESCE(SUM(quantity_on_hand), 0) FROM potions")
        ).one()

        gold = inventory.gold
        total_ml = (
            inventory.red_ml
            + inventory.green_ml
            + inventory.blue_ml
            + inventory.dark_ml
        )
        total_potions = potions_result[0]
        max_potion_capacity = inventory.max_potion_capacity
        max_ml_capacity = inventory.max_barrel_capacity

        # Current capacity in units (1 unit = 50 potions or 10000 ml)
        current_potion_units = max_potion_capacity // 50
        current_ml_units = max_ml_capacity // 10000

        # Utilization percentages
        potion_utilization = total_potions / max_potion_capacity
        ml_utilization = total_ml / max_ml_capacity

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

    with db.engine.begin() as connection:
        # Deduct gold and increase capacity
        connection.execute(
            sqlalchemy.text(
                """UPDATE global_inventory SET
                   gold = gold - :total_cost,
                   max_potion_capacity = max_potion_capacity + :potion_capacity_increase,
                   max_barrel_capacity = max_barrel_capacity + :ml_capacity_increase
                """
            ),
            {
                "total_cost": total_cost,
                "potion_capacity_increase": capacity_purchase.potion_capacity * 50,
                "ml_capacity_increase": capacity_purchase.ml_capacity * 10000,
            },
        )
