from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field, field_validator
from typing import List
from src.api import auth
from src import database as db
import sqlalchemy

router = APIRouter(
    prefix="/bottler",
    tags=["bottler"],
    dependencies=[Depends(auth.get_api_key)],
)


class PotionMixes(BaseModel):
    potion_type: List[int] = Field(
        ...,
        min_length=4,
        max_length=4,
        description="Must contain exactly 4 elements: [r, g, b, d]",
    )
    quantity: int = Field(
        ..., ge=1, le=10000, description="Quantity must be between 1 and 10,000"
    )

    @field_validator("potion_type")
    @classmethod
    def validate_potion_type(cls, potion_type: List[int]) -> List[int]:
        if sum(potion_type) != 100:
            raise ValueError("Sum of potion_type values must be exactly 100")
        return potion_type


@router.post("/deliver/{order_id}", status_code=status.HTTP_204_NO_CONTENT)
def post_deliver_bottles(potions_delivered: List[PotionMixes], order_id: int):
    """
    Delivery of potions requested after plan. order_id is a unique value representing
    a single delivery; the call is idempotent based on the order_id.
    """
    print(f"potions delivered: {potions_delivered} order_id: {order_id}")

    request_id = f"bottler_deliver_{order_id}"

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

        # Create a potion transaction
        potion_transaction = connection.execute(
            sqlalchemy.text(
                """INSERT INTO potion_transactions (description) 
                   VALUES (:description) 
                   RETURNING id"""
            ),
            {"description": f"Bottled {sum(p.quantity for p in potions_delivered)} potions"},
        ).one()
        potion_transaction_id = potion_transaction.id

        total_red_used = 0
        total_green_used = 0
        total_blue_used = 0
        total_dark_used = 0

        for potion_mix in potions_delivered:
            recipe = potion_mix.potion_type
            quantity = potion_mix.quantity

            # Find existing potion with this recipe
            result = connection.execute(
                sqlalchemy.text(
                    """SELECT id FROM potions 
                       WHERE red_ml = :red_ml AND green_ml = :green_ml 
                         AND blue_ml = :blue_ml AND dark_ml = :dark_ml"""
                ),
                {
                    "red_ml": recipe[0],
                    "green_ml": recipe[1],
                    "blue_ml": recipe[2],
                    "dark_ml": recipe[3],
                },
            ).fetchone()

            if result:
                potion_id = result.id
            else:
                # If this recipe is new, create it
                generated_sku = f"MIX_{recipe[0]}_{recipe[1]}_{recipe[2]}_{recipe[3]}"
                generated_name = (
                    f"Custom Mix {recipe[0]}-{recipe[1]}-{recipe[2]}-{recipe[3]}"
                )
                result = connection.execute(
                    sqlalchemy.text(
                        """
                        INSERT INTO potions
                            (sku, name, quantity_on_hand, price, red_ml, green_ml, blue_ml, dark_ml)
                        VALUES
                            (:sku, :name, :quantity, :price, :red_ml, :green_ml, :blue_ml, :dark_ml)
                        ON CONFLICT (sku)
                        DO UPDATE SET quantity_on_hand = potions.quantity_on_hand + EXCLUDED.quantity_on_hand
                        RETURNING id
                        """
                    ),
                    {
                        "sku": generated_sku,
                        "name": generated_name,
                        "quantity": 0,  # Don't use quantity_on_hand anymore, use ledger
                        "price": 50,
                        "red_ml": recipe[0],
                        "green_ml": recipe[1],
                        "blue_ml": recipe[2],
                        "dark_ml": recipe[3],
                    },
                ).one()
                potion_id = result.id

            # Add potion ledger entry (positive because we're adding potions)
            connection.execute(
                sqlalchemy.text(
                    """INSERT INTO potion_ledger_entries (potion_id, potion_transaction_id, change) 
                       VALUES (:potion_id, :transaction_id, :change)"""
                ),
                {"potion_id": potion_id, "transaction_id": potion_transaction_id, "change": quantity},
            )

            # Track ml used
            total_red_used += recipe[0] * quantity
            total_green_used += recipe[1] * quantity
            total_blue_used += recipe[2] * quantity
            total_dark_used += recipe[3] * quantity

        # Create an ml transaction for the deduction
        ml_transaction = connection.execute(
            sqlalchemy.text(
                """INSERT INTO ml_transactions (description) 
                   VALUES (:description) 
                   RETURNING id"""
            ),
            {"description": "Used ML to bottle potions"},
        ).one()
        ml_transaction_id = ml_transaction.id

        # Add ml ledger entries for each color used (negative because we're removing ml)
        if total_red_used > 0:
            connection.execute(
                sqlalchemy.text(
                    """INSERT INTO ml_ledger_entries (ml_transaction_id, color, change) 
                       VALUES (:transaction_id, :color, :change)"""
                ),
                {"transaction_id": ml_transaction_id, "color": "red", "change": -total_red_used},
            )
        if total_green_used > 0:
            connection.execute(
                sqlalchemy.text(
                    """INSERT INTO ml_ledger_entries (ml_transaction_id, color, change) 
                       VALUES (:transaction_id, :color, :change)"""
                ),
                {"transaction_id": ml_transaction_id, "color": "green", "change": -total_green_used},
            )
        if total_blue_used > 0:
            connection.execute(
                sqlalchemy.text(
                    """INSERT INTO ml_ledger_entries (ml_transaction_id, color, change) 
                       VALUES (:transaction_id, :color, :change)"""
                ),
                {"transaction_id": ml_transaction_id, "color": "blue", "change": -total_blue_used},
            )
        if total_dark_used > 0:
            connection.execute(
                sqlalchemy.text(
                    """INSERT INTO ml_ledger_entries (ml_transaction_id, color, change) 
                       VALUES (:transaction_id, :color, :change)"""
                ),
                {"transaction_id": ml_transaction_id, "color": "dark", "change": -total_dark_used},
            )

        # Store the processed request
        connection.execute(
            sqlalchemy.text(
                """INSERT INTO processed_requests (request_id, response) 
                   VALUES (:request_id, :response)"""
            ),
            {"request_id": request_id, "response": sqlalchemy.JSON.cache_ok},
        )


def create_bottle_plan(
    recipes: List[tuple],
    red_ml: int,
    green_ml: int,
    blue_ml: int,
    dark_ml: int,
    maximum_potion_capacity: int,
) -> List[PotionMixes]:
    """
    Create a bottling plan by trying to brew each available recipe.
    recipes is list of (red_ml, green_ml, blue_ml, dark_ml) tuples
    """
    remaining_potion_capacity = maximum_potion_capacity
    plan: List[PotionMixes] = []

    for recipe in recipes:
        if remaining_potion_capacity <= 0:
            break

        red_needed, green_needed, blue_needed, dark_needed = recipe

        # Calculate how many we can make of this recipe
        max_by_red = red_ml // red_needed if red_needed > 0 else float("inf")
        max_by_green = green_ml // green_needed if green_needed > 0 else float("inf")
        max_by_blue = blue_ml // blue_needed if blue_needed > 0 else float("inf")
        max_by_dark = dark_ml // dark_needed if dark_needed > 0 else float("inf")

        max_brewable = int(min(max_by_red, max_by_green, max_by_blue, max_by_dark))

        if max_brewable <= 0:
            continue

        quantity_to_bottle = min(max_brewable, remaining_potion_capacity)

        plan.append(PotionMixes(potion_type=list(recipe), quantity=quantity_to_bottle))

        red_ml -= red_needed * quantity_to_bottle
        green_ml -= green_needed * quantity_to_bottle
        blue_ml -= blue_needed * quantity_to_bottle
        dark_ml -= dark_needed * quantity_to_bottle
        remaining_potion_capacity -= quantity_to_bottle

    return plan


@router.post("/plan", response_model=List[PotionMixes])
def get_bottle_plan():
    """
    Gets the plan for bottling potions.
    Loads available recipes from the potions table and calculates optimal bottling plan.
    """
    with db.engine.begin() as connection:
        # Get ml available from ledger
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

        # Get potion quantities from ledger
        potion_quantities = connection.execute(
            sqlalchemy.text(
                """SELECT potion_id, COALESCE(SUM(change), 0) as quantity_on_hand
                   FROM potion_ledger_entries
                   GROUP BY potion_id"""
            )
        ).fetchall()

        # Calculate total potion capacity used
        total_potions = sum(p.quantity_on_hand for p in potion_quantities)

        # Get max potion capacity
        capacity_result = connection.execute(
            sqlalchemy.text(
                "SELECT max_potion_capacity FROM global_inventory"
            )
        ).one()

        remaining_potion_capacity = capacity_result.max_potion_capacity - total_potions

        red_ml = ml_result.red_ml
        green_ml = ml_result.green_ml
        blue_ml = ml_result.blue_ml
        dark_ml = ml_result.dark_ml

        # Get all available recipes from potions table, ordered by price (highest first)
        recipes = connection.execute(
            sqlalchemy.text(
                """SELECT red_ml, green_ml, blue_ml, dark_ml, price
                   FROM potions ORDER BY price DESC"""
            )
        ).fetchall()

        # Convert to list of tuples for create_bottle_plan (sorted by value/price)
        recipe_list = [(r.red_ml, r.green_ml, r.blue_ml, r.dark_ml) for r in recipes]

    return create_bottle_plan(
        recipes=recipe_list,
        red_ml=red_ml,
        green_ml=green_ml,
        blue_ml=blue_ml,
        dark_ml=dark_ml,
        maximum_potion_capacity=remaining_potion_capacity,
    )


if __name__ == "__main__":
    print(get_bottle_plan())
