from dataclasses import dataclass
from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field, field_validator
from typing import List
import json

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
    return BarrelSummary(
        gold_paid=sum(b.price * b.quantity for b in barrels),
        red_ml=sum(
            int(b.ml_per_barrel * b.potion_type[0]) * b.quantity for b in barrels
        ),
        green_ml=sum(
            int(b.ml_per_barrel * b.potion_type[1]) * b.quantity for b in barrels
        ),
        blue_ml=sum(
            int(b.ml_per_barrel * b.potion_type[2]) * b.quantity for b in barrels
        ),
        dark_ml=sum(
            int(b.ml_per_barrel * b.potion_type[3]) * b.quantity for b in barrels
        ),
    )


@router.post("/deliver/{order_id}", status_code=status.HTTP_204_NO_CONTENT)
def post_deliver_barrels(barrels_delivered: List[Barrel], order_id: int):
    """
    Processes barrels delivered based on the provided order_id. order_id is a unique value representing
    a single delivery; the call is idempotent based on the order_id.
    """
    print(f"barrels delivered: {barrels_delivered} order_id: {order_id}")

    delivery = calculate_barrel_summary(barrels_delivered)
    request_id = f"barrels_deliver_{order_id}"

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

        # Create a gold transaction
        gold_transaction = connection.execute(
            sqlalchemy.text(
                """INSERT INTO gold_transactions (description) 
                   VALUES (:description) 
                   RETURNING id"""
            ),
            {"description": f"Bought barrels for {delivery.gold_paid} gold"},
        ).one()
        gold_transaction_id = gold_transaction.id

        # Add gold ledger entry (negative because we're spending gold)
        connection.execute(
            sqlalchemy.text(
                """INSERT INTO gold_ledger_entries (gold_transaction_id, change) 
                   VALUES (:transaction_id, :change)"""
            ),
            {"transaction_id": gold_transaction_id, "change": -delivery.gold_paid},
        )

        # Create an ml transaction
        ml_transaction = connection.execute(
            sqlalchemy.text(
                """INSERT INTO ml_transactions (description) 
                   VALUES (:description) 
                   RETURNING id"""
            ),
            {"description": "Received barrels with ML"},
        ).one()
        ml_transaction_id = ml_transaction.id

        # Add ml ledger entries for each color
        if delivery.red_ml > 0:
            connection.execute(
                sqlalchemy.text(
                    """INSERT INTO ml_ledger_entries (ml_transaction_id, color, change) 
                       VALUES (:transaction_id, :color, :change)"""
                ),
                {
                    "transaction_id": ml_transaction_id,
                    "color": "red",
                    "change": delivery.red_ml,
                },
            )
        if delivery.green_ml > 0:
            connection.execute(
                sqlalchemy.text(
                    """INSERT INTO ml_ledger_entries (ml_transaction_id, color, change) 
                       VALUES (:transaction_id, :color, :change)"""
                ),
                {
                    "transaction_id": ml_transaction_id,
                    "color": "green",
                    "change": delivery.green_ml,
                },
            )
        if delivery.blue_ml > 0:
            connection.execute(
                sqlalchemy.text(
                    """INSERT INTO ml_ledger_entries (ml_transaction_id, color, change) 
                       VALUES (:transaction_id, :color, :change)"""
                ),
                {
                    "transaction_id": ml_transaction_id,
                    "color": "blue",
                    "change": delivery.blue_ml,
                },
            )
        if delivery.dark_ml > 0:
            connection.execute(
                sqlalchemy.text(
                    """INSERT INTO ml_ledger_entries (ml_transaction_id, color, change) 
                       VALUES (:transaction_id, :color, :change)"""
                ),
                {
                    "transaction_id": ml_transaction_id,
                    "color": "dark",
                    "change": delivery.dark_ml,
                },
            )

        # Store the processed request
        connection.execute(
            sqlalchemy.text(
                """INSERT INTO processed_requests (request_id, response) 
                   VALUES (:request_id, :response)"""
            ),
            {"request_id": request_id, "response": json.dumps({})},
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

    color_index = {
        "red": 0,
        "green": 1,
        "blue": 2,
        "dark": 3,
    }
    current_ml = {
        "red": current_red_ml,
        "green": current_green_ml,
        "blue": current_blue_ml,
        "dark": current_dark_ml,
    }

    colors_by_scarcity = sorted(current_ml, key=lambda color: current_ml[color])

    remaining_gold = gold
    remaining_capacity = max_barrel_capacity
    remaining_quantity_by_sku = {
        barrel.sku: barrel.quantity for barrel in wholesale_catalog
    }
    orders: List[BarrelOrder] = []

    for color in colors_by_scarcity:
        color_idx = color_index[color]

        eligible_barrels = [
            barrel
            for barrel in wholesale_catalog
            if int(barrel.ml_per_barrel * barrel.potion_type[color_idx]) > 0
        ]
        # Prioritize barrels that provide the most of the current scarce color.
        eligible_barrels.sort(
            key=lambda barrel: (
                int(barrel.ml_per_barrel * barrel.potion_type[color_idx]),
                -barrel.price,
            ),
            reverse=True,
        )

        for barrel in eligible_barrels:
            if barrel.price <= 0:
                continue

            max_by_gold = remaining_gold // barrel.price
            max_by_capacity = remaining_capacity // barrel.ml_per_barrel
            quantity_to_buy = min(
                remaining_quantity_by_sku[barrel.sku], max_by_gold, max_by_capacity
            )

            if quantity_to_buy <= 0:
                continue

            orders.append(BarrelOrder(sku=barrel.sku, quantity=quantity_to_buy))
            remaining_quantity_by_sku[barrel.sku] -= quantity_to_buy
            remaining_gold -= quantity_to_buy * barrel.price
            remaining_capacity -= quantity_to_buy * barrel.ml_per_barrel

            if remaining_gold <= 0 or remaining_capacity <= 0:
                return orders

    return orders


@router.post("/plan", response_model=List[BarrelOrder])
def get_wholesale_purchase_plan(wholesale_catalog: List[Barrel]):
    """
    Gets the plan for purchasing wholesale barrels. The call passes in a catalog of available barrels
    and the shop returns back which barrels they'd like to purchase and how many.
    """
    print(f"barrel catalog: {wholesale_catalog}")

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

        # Get capacity from global_inventory
        capacity_result = connection.execute(
            sqlalchemy.text("SELECT max_barrel_capacity FROM global_inventory")
        ).one()

        max_barrel_capacity = capacity_result.max_barrel_capacity
        # Calculate remaining capacity
        total_ml_used = (
            ml_result.red_ml
            + ml_result.green_ml
            + ml_result.blue_ml
            + ml_result.dark_ml
        )
        remaining_barrel_capacity = max_barrel_capacity - total_ml_used

        red_ml = ml_result.red_ml
        green_ml = ml_result.green_ml
        blue_ml = ml_result.blue_ml
        dark_ml = ml_result.dark_ml

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
