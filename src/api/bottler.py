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

    with db.engine.begin() as connection:
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
                # Increment quantity on hand
                connection.execute(
                    sqlalchemy.text(
                        "UPDATE potions SET quantity_on_hand = quantity_on_hand + :qty WHERE id = :id"
                    ),
                    {"qty": quantity, "id": potion_id},
                )

            # Deduct ml from global_inventory based on recipe used
            connection.execute(
                sqlalchemy.text(
                    """UPDATE global_inventory SET 
                       red_ml = red_ml - :red_used,
                       green_ml = green_ml - :green_used,
                       blue_ml = blue_ml - :blue_used,
                       dark_ml = dark_ml - :dark_used"""
                ),
                {
                    "red_used": recipe[0] * quantity,
                    "green_used": recipe[1] * quantity,
                    "blue_used": recipe[2] * quantity,
                    "dark_used": recipe[3] * quantity,
                },
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
        # Get ml available and total potion capacity
        result = connection.execute(
            sqlalchemy.text(
                """SELECT g.max_potion_capacity - COALESCE(SUM(p.quantity_on_hand), 0) AS remaining_potion_capacity,
                          g.red_ml, g.green_ml, g.blue_ml, g.dark_ml
                   FROM global_inventory g
                   LEFT JOIN potions p ON TRUE
                   GROUP BY g.id, g.max_potion_capacity, g.red_ml, g.green_ml, g.blue_ml, g.dark_ml"""
            )
        ).one()

        remaining_potion_capacity = result.remaining_potion_capacity
        red_ml = result.red_ml
        green_ml = result.green_ml
        blue_ml = result.blue_ml
        dark_ml = result.dark_ml

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
