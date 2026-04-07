from dataclasses import dataclass
from random import choice
from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field, field_validator
from typing import List

import sqlalchemy
from src.api import auth
from src import database as db

router = APIRouter(
    prefix="/barrels",
    tags=["barrels"],
    dependencies=[Depends(auth.get_api_key)],
)


class Barrel(BaseModel):
    sku: str
    ml_per_barrel: int = Field(gt=0, description="Must be greater than 0")
    potion_type: List[float] = Field(
        ...,
        min_length=4,
        max_length=4,
        description="Must contain exactly 4 elements: [r, g, b, d] that sum to 1.0",
    )
    price: int = Field(ge=0, description="Price must be non-negative")
    quantity: int = Field(ge=0, description="Quantity must be non-negative")

    @field_validator("potion_type")
    @classmethod
    def validate_potion_type(cls, potion_type: List[float]) -> List[float]:
        if len(potion_type) != 4:
            raise ValueError("potion_type must have exactly 4 elements: [r, g, b, d]")
        if not abs(sum(potion_type) - 1.0) < 1e-6:
            raise ValueError("Sum of potion_type values must be exactly 1.0")
        return potion_type


class BarrelOrder(BaseModel):
    sku: str
    quantity: int = Field(gt=0, description="Quantity must be greater than 0")


@dataclass
class BarrelSummary:
    gold_paid: int
    red_ml: int
    green_ml: int
    blue_ml: int
    dark_ml: int


def calculate_barrel_summary(barrels: List[Barrel]) -> BarrelSummary:
    return BarrelSummary(gold_paid=sum(b.price * b.quantity for b in barrels),
                            red_ml=sum(int(b.ml_per_barrel * b.potion_type[0]) * b.quantity for b in barrels),
                            green_ml=sum(int(b.ml_per_barrel * b.potion_type[1]) * b.quantity for b in barrels),
                            blue_ml=sum(int(b.ml_per_barrel * b.potion_type[2]) * b.quantity for b in barrels),
                            dark_ml=sum(int(b.ml_per_barrel * b.potion_type[3]) * b.quantity for b in barrels))



@router.post("/deliver/{order_id}", status_code=status.HTTP_204_NO_CONTENT)
def post_deliver_barrels(barrels_delivered: List[Barrel], order_id: int):
    """
    Processes barrels delivered based on the provided order_id. order_id is a unique value representing
    a single delivery; the call is idempotent based on the order_id.
    """
    print(f"barrels delivered: {barrels_delivered} order_id: {order_id}")

    delivery = calculate_barrel_summary(barrels_delivered)

    with db.engine.begin() as connection:
        connection.execute(
            sqlalchemy.text(
                """
                UPDATE global_inventory SET 
                gold = gold - :gold_paid,
                red_ml = red_ml + :delivered_red_ml,
                green_ml = green_ml + :delivered_green_ml,
                blue_ml = blue_ml + :delivered_blue_ml,
                dark_ml = dark_ml + :delivered_dark_ml
                """
            ),
            {"gold_paid": delivery.gold_paid,
             "delivered_red_ml": delivery.red_ml,
             "delivered_green_ml": delivery.green_ml,
             "delivered_blue_ml": delivery.blue_ml,
             "delivered_dark_ml": delivery.dark_ml}
        )

def create_barrel_plan(
    gold: int,
    max_barrel_capacity: int,
    current_red_ml: int,
    current_green_ml: int,
    current_blue_ml: int,
    current_dark_ml: int,
    wholesale_catalog: List[Barrel],
) -> List[BarrelOrder]:
    print(
        f"gold: {gold}, max_barrel_capacity: {max_barrel_capacity}, current_red_ml: {current_red_ml}, current_green_ml: {current_green_ml}, current_blue_ml: {current_blue_ml}, current_dark_ml: {current_dark_ml}, wholesale_catalog: {wholesale_catalog}"
    )

    color = choice(["red", "green", "blue", "dark"])

    with db.engine.begin() as connection:
        result = connection.execute(
            sqlalchemy.text(
                """ SELECT red_potions, green_potions, blue_potions, dark_potions FROM global_inventory """
            )
        ).one()

        current_red_potions = result.red_potions
        current_green_potions = result.green_potions
        current_blue_potions = result.blue_potions
        current_dark_potions = result.dark_potions
    current_potions = {
        "red": current_red_potions,
        "green": current_green_potions,
        "blue": current_blue_potions,
        "dark": current_dark_potions,
    }

    # Version 1 rule: only buy a barrel for the randomly chosen color if we have < 5 potions.
    if current_potions[color] >= 5:
        return []

    color_index = {
        "red": 0,
        "green": 1,
        "blue": 2,
        "dark": 3,
    }

    chosen_index = color_index[color]

    cheapest_chosen_barrel = min(
        (
            barrel
            for barrel in wholesale_catalog
                if barrel.potion_type[chosen_index] == 1 and barrel.ml_per_barrel <= max_barrel_capacity
        ),
        key=lambda b: b.price,
        default=None,
    )

    if cheapest_chosen_barrel and cheapest_chosen_barrel.price <= gold:
        return [BarrelOrder(sku=cheapest_chosen_barrel.sku, quantity=1)]

    # return an empty list if no affordable barrel is found
    return []


@router.post("/plan", response_model=List[BarrelOrder])
def get_wholesale_purchase_plan(wholesale_catalog: List[Barrel]):
    """
    Gets the plan for purchasing wholesale barrels. The call passes in a catalog of available barrels
    and the shop returns back which barrels they'd like to purchase and how many.
    """
    print(f"barrel catalog: {wholesale_catalog}")

    sql_to_execute = """ SELECT gold, max_barrel_capacity - (red_ml + green_ml + blue_ml + dark_ml) AS remaining_barrel_capacity, red_ml, green_ml, blue_ml, dark_ml, red_potions, green_potions, blue_potions, dark_potions FROM global_inventory """

    with db.engine.begin() as connection:
        result = connection.execute(sqlalchemy.text(sql_to_execute)).one()
        gold = result.gold
        remaining_barrel_capacity = result.remaining_barrel_capacity
        red_ml = result.red_ml
        green_ml = result.green_ml
        blue_ml = result.blue_ml
        dark_ml = result.dark_ml

    # TODO: fill in values correctly based on what is in your database
    return create_barrel_plan(
        gold=gold,
        max_barrel_capacity=remaining_barrel_capacity,
        current_red_ml=red_ml,
        current_green_ml=green_ml,
        current_blue_ml=blue_ml,
        current_dark_ml=dark_ml,
        wholesale_catalog=wholesale_catalog,
    )
