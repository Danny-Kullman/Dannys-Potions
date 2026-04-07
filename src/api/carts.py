from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
import sqlalchemy
from src.api import auth
from enum import Enum
from typing import List, Optional
from src import database as db

router = APIRouter(
    prefix="/carts",
    tags=["cart"],
    dependencies=[Depends(auth.get_api_key)],
)


class SearchSortOptions(str, Enum):
    customer_name = "customer_name"
    item_sku = "item_sku"
    line_item_total = "line_item_total"
    timestamp = "timestamp"


class SearchSortOrder(str, Enum):
    asc = "asc"
    desc = "desc"


class LineItem(BaseModel):
    line_item_id: int
    item_sku: str
    customer_name: str
    line_item_total: int
    timestamp: str


class SearchResponse(BaseModel):
    previous: Optional[str] = None
    next: Optional[str] = None
    results: List[LineItem]


@router.get("/search/", response_model=SearchResponse, tags=["search"])
def search_orders(
    customer_name: str = "",
    potion_sku: str = "",
    search_page: str = "",
    sort_col: SearchSortOptions = SearchSortOptions.timestamp,
    sort_order: SearchSortOrder = SearchSortOrder.desc,
):
    """
    Search for cart line items by customer name and/or potion sku.
    """
    return SearchResponse(
        previous=None,
        next=None,
        results=[
            LineItem(
                line_item_id=1,
                item_sku="1 oblivion potion",
                customer_name="Scaramouche",
                line_item_total=50,
                timestamp="2021-01-01T00:00:00Z",
            )
        ],
    )


cart_id_counter = 1
carts: dict[int, dict[str, int]] = {}


class Customer(BaseModel):
    customer_id: str
    customer_name: str
    character_class: str
    character_species: str
    level: int = Field(ge=1, le=20)


@router.post("/visits/{visit_id}", status_code=status.HTTP_204_NO_CONTENT)
def post_visits(visit_id: int, customers: List[Customer]):
    """
    Shares the customers that visited the store on that tick.
    """
    print(customers)
    pass


class CartCreateResponse(BaseModel):
    cart_id: int


@router.post("/", response_model=CartCreateResponse)
def create_cart(new_cart: Customer):
    """
    Creates a new cart for a specific customer.
    """
    global cart_id_counter
    cart_id = cart_id_counter
    cart_id_counter += 1
    carts[cart_id] = {}
    return CartCreateResponse(cart_id=cart_id)


class CartItem(BaseModel):
    quantity: int = Field(ge=1, description="Quantity must be at least 1")


@router.post("/{cart_id}/items/{item_sku}", status_code=status.HTTP_204_NO_CONTENT)
def set_item_quantity(cart_id: int, item_sku: str, cart_item: CartItem):
    print(
        f"cart_id: {cart_id}, item_sku: {item_sku}, cart_item: {cart_item}, carts: {carts}"
    )
    if cart_id not in carts:
        raise HTTPException(status_code=404, detail="Cart not found")

    carts[cart_id][item_sku] = cart_item.quantity
    return status.HTTP_204_NO_CONTENT


class CheckoutResponse(BaseModel):
    total_potions_bought: int
    total_gold_paid: int


class CartCheckout(BaseModel):
    payment: str


@router.post("/{cart_id}/checkout", response_model=CheckoutResponse)
def checkout(cart_id: int, cart_checkout: CartCheckout):
    """
    Handles the checkout process for a specific cart.
    """

    if cart_id not in carts:
        raise HTTPException(status_code=404, detail="Cart not found")

    total_potions_bought = sum(carts[cart_id].values())
    total_gold_paid = total_potions_bought * 50  # Assuming each potion costs 50 gold

    potion_totals = {
        "red": 0,
        "green": 0,
        "blue": 0,
        "dark": 0,
    }

    for item_sku, quantity in carts[cart_id].items():
        item_sku_lower = item_sku.lower()
        if "red" in item_sku_lower:
            potion_totals["red"] += quantity
        elif "green" in item_sku_lower:
            potion_totals["green"] += quantity
        elif "blue" in item_sku_lower:
            potion_totals["blue"] += quantity
        elif "dark" in item_sku_lower:
            potion_totals["dark"] += quantity
        else:
            raise HTTPException(status_code=400, detail=f"Unknown potion SKU: {item_sku}")

    with db.engine.begin() as connection:
        row = connection.execute(
            sqlalchemy.text(
                """
                SELECT gold, red_potions, green_potions, blue_potions, dark_potions FROM global_inventory
                """
            )
        ).one()

        if row.red_potions < potion_totals["red"]:
            raise HTTPException(status_code=400, detail="Not enough red potions in inventory")
        if row.green_potions < potion_totals["green"]:
            raise HTTPException(status_code=400, detail="Not enough green potions in inventory")
        if row.blue_potions < potion_totals["blue"]:
            raise HTTPException(status_code=400, detail="Not enough blue potions in inventory")
        if row.dark_potions < potion_totals["dark"]:
            raise HTTPException(status_code=400, detail="Not enough dark potions in inventory")

        connection.execute(
            sqlalchemy.text(
                """
                UPDATE global_inventory SET 
                gold = gold + :total_gold_paid,
                red_potions = red_potions - :red_potions,
                green_potions = green_potions - :green_potions,
                blue_potions = blue_potions - :blue_potions,
                dark_potions = dark_potions - :dark_potions
                """
            ),
            {
                "total_gold_paid": total_gold_paid,
                "red_potions": potion_totals["red"],
                "green_potions": potion_totals["green"],
                "blue_potions": potion_totals["blue"],
                "dark_potions": potion_totals["dark"],
            },
        )
    # TODO: Deduct the right potions from inventory to the shop

    carts[cart_id] = {}



    return CheckoutResponse(
        total_potions_bought=total_potions_bought, total_gold_paid=total_gold_paid
    )
