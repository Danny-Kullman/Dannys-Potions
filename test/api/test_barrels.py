from src.api.barrels import (
    calculate_barrel_summary,
    create_barrel_plan,
    Barrel,
    BarrelOrder,
)
from typing import List


def test_barrel_delivery() -> None:
    delivery: List[Barrel] = [
        Barrel(
            sku="SMALL_RED_BARREL",
            ml_per_barrel=1000,
            potion_type=[1.0, 0, 0, 0],
            price=100,
            quantity=10,
        ),
        Barrel(
            sku="SMALL_GREEN_BARREL",
            ml_per_barrel=1000,
            potion_type=[0, 1.0, 0, 0],
            price=150,
            quantity=5,
        ),
    ]

    delivery_summary = calculate_barrel_summary(delivery)

    assert delivery_summary.gold_paid == 1750


def test_buy_small_red_barrel_plan() -> None:
    wholesale_catalog: List[Barrel] = [
        Barrel(
            sku="SMALL_RED_BARREL",
            ml_per_barrel=1000,
            potion_type=[1.0, 0, 0, 0],
            price=100,
            quantity=10,
        ),
        Barrel(
            sku="SMALL_GREEN_BARREL",
            ml_per_barrel=1000,
            potion_type=[0, 1.0, 0, 0],
            price=100,
            quantity=5,
        ),
        Barrel(
            sku="SMALL_BLUE_BARREL",
            ml_per_barrel=1000,
            potion_type=[0, 0, 1.0, 0],
            price=100,
            quantity=2,
        ),
        Barrel(
            sku="SMALL_DARK_BARREL",
            ml_per_barrel=1000,
            potion_type=[0, 0, 0, 1.0],
            price=100,
            quantity=2,
        ),
    ]

    gold = 100
    max_barrel_capacity = 10000
    current_red_ml = 0
    current_green_ml = 1000
    current_blue_ml = 1000
    current_dark_ml = 1000

    barrel_orders = create_barrel_plan(
        gold,
        max_barrel_capacity,
        current_red_ml,
        current_green_ml,
        current_blue_ml,
        current_dark_ml,
        wholesale_catalog,
    )

    assert isinstance(barrel_orders, list)
    assert all(isinstance(order, BarrelOrder) for order in barrel_orders)
    assert len(barrel_orders) > 0  # Ensure at least one order is generated
    assert barrel_orders[0].quantity == 1  # Placeholder quantity assertion


def test_cant_afford_barrel_plan() -> None:
    wholesale_catalog: List[Barrel] = [
        Barrel(
            sku="SMALL_RED_BARREL",
            ml_per_barrel=1000,
            potion_type=[1.0, 0, 0, 0],
            price=100,
            quantity=10,
        ),
        Barrel(
            sku="SMALL_GREEN_BARREL",
            ml_per_barrel=1000,
            potion_type=[0, 1.0, 0, 0],
            price=150,
            quantity=5,
        ),
        Barrel(
            sku="SMALL_BLUE_BARREL",
            ml_per_barrel=1000,
            potion_type=[0, 0, 1.0, 0],
            price=500,
            quantity=2,
        ),
    ]

    gold = 50
    max_barrel_capacity = 10000
    current_red_ml = 0
    current_green_ml = 1000
    current_blue_ml = 1000
    current_dark_ml = 1000

    barrel_orders = create_barrel_plan(
        gold,
        max_barrel_capacity,
        current_red_ml,
        current_green_ml,
        current_blue_ml,
        current_dark_ml,
        wholesale_catalog,
    )

    assert isinstance(barrel_orders, list)
    assert all(isinstance(order, BarrelOrder) for order in barrel_orders)
    assert len(barrel_orders) == 0  # Ensure at least one order is generated


def test_buy_by_scarcity_until_gold_exhausted() -> None:
    wholesale_catalog: List[Barrel] = [
        Barrel(
            sku="RED_GREEN_MIX",
            ml_per_barrel=1000,
            potion_type=[0.6, 0.4, 0, 0],
            price=30,
            quantity=1,
        ),
        Barrel(
            sku="GREEN_ONLY",
            ml_per_barrel=1000,
            potion_type=[0, 1.0, 0, 0],
            price=20,
            quantity=1,
        ),
        Barrel(
            sku="BLUE_ONLY",
            ml_per_barrel=1000,
            potion_type=[0, 0, 1.0, 0],
            price=20,
            quantity=1,
        ),
        Barrel(
            sku="DARK_ONLY",
            ml_per_barrel=1000,
            potion_type=[0, 0, 0, 1.0],
            price=30,
            quantity=1,
        ),
    ]

    barrel_orders = create_barrel_plan(
        gold=100,
        max_barrel_capacity=10000,
        current_red_ml=0,
        current_green_ml=100,
        current_blue_ml=200,
        current_dark_ml=300,
        wholesale_catalog=wholesale_catalog,
    )

    assert [order.sku for order in barrel_orders] == [
        "RED_GREEN_MIX",
        "GREEN_ONLY",
        "BLUE_ONLY",
        "DARK_ONLY",
    ]
    assert [order.quantity for order in barrel_orders] == [1, 1, 1, 1]
