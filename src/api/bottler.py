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

    red_potions, green_potions, blue_potions, dark_potions = 0, 0, 0, 0
    for PotionMix in potions_delivered:
        if PotionMix.potion_type[0] == 100:
            red_potions += PotionMix.quantity
        elif PotionMix.potion_type[1] == 100:
            green_potions += PotionMix.quantity
        elif PotionMix.potion_type[2] == 100:
            blue_potions += PotionMix.quantity
        elif PotionMix.potion_type[3] == 100:
            dark_potions += PotionMix.quantity

    # Record values of delivered potions in your database
    # and Subtract ml based on how much delivered potions used.

    with db.engine.begin() as connection:
        connection.execute(
            sqlalchemy.text(
                """
                UPDATE global_inventory SET 
                red_potions = red_potions + :red_potions,
                green_potions = green_potions + :green_potions,
                blue_potions = blue_potions + :blue_potions,
                dark_potions = dark_potions + :dark_potions,
                red_ml = red_ml - (100 * :red_potions),
                green_ml = green_ml - (100 * :green_potions),
                blue_ml = blue_ml - (100 * :blue_potions),
                dark_ml = dark_ml - (100 * :dark_potions)
                """
            ),
            {"red_potions": red_potions,
             "green_potions": green_potions,
             "blue_potions": blue_potions,
             "dark_potions": dark_potions},
        )

def create_bottle_plan(
    red_ml: int,
    green_ml: int,
    blue_ml: int,
    dark_ml: int,
    maximum_potion_capacity: int,
) -> List[PotionMixes]:
    
    possible_by_color = [
        ([100, 0, 0, 0], red_ml // 100),
        ([0, 100, 0, 0], green_ml // 100),
        ([0, 0, 100, 0], blue_ml // 100),
        ([0, 0, 0, 100], dark_ml // 100),
    ]

    remaining_potion_capacity = maximum_potion_capacity
    plan: List[PotionMixes] = []

    for potion_type, possible_quantity in possible_by_color:
        if remaining_potion_capacity <= 0:
            break

        quantity_to_bottle = min(possible_quantity, remaining_potion_capacity)
        if quantity_to_bottle > 0:
            plan.append(PotionMixes(potion_type=potion_type, quantity=quantity_to_bottle))
            remaining_potion_capacity -= quantity_to_bottle

    return plan


@router.post("/plan", response_model=List[PotionMixes])
def get_bottle_plan():
    """
    Gets the plan for bottling potions.
    Each bottle has a quantity of what proportion of red, green, blue, and dark potions to add.
    Colors are expressed in integers from 0 to 100 that must sum up to exactly 100.
    """


    sql_to_execute = """ SELECT max_potion_capacity - (red_potions + green_potions + blue_potions + dark_potions) AS remaining_potion_capacity, red_ml, green_ml, blue_ml, dark_ml, red_potions, green_potions, blue_potions, dark_potions FROM global_inventory """

    with db.engine.begin() as connection:
        result = connection.execute(sqlalchemy.text(sql_to_execute)).one()
        remaining_potion_capacity = result.remaining_potion_capacity
        red_ml = result.red_ml
        green_ml = result.green_ml
        blue_ml = result.blue_ml
        dark_ml = result.dark_ml

    # TODO: Fill in values below based on what is in your database
    return create_bottle_plan(
        red_ml=red_ml,
        green_ml=green_ml,
        blue_ml=blue_ml,
        dark_ml=dark_ml,
        maximum_potion_capacity=remaining_potion_capacity,
    )


if __name__ == "__main__":
    print(get_bottle_plan())
