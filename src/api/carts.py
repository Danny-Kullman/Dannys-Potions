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


# In-memory carts removed - now using database tables (carts, cart_items)


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
    with db.engine.begin() as connection:
        result = connection.execute(
            sqlalchemy.text(
                """INSERT INTO carts (customer_id, customer_name, character_class, character_species, character_level)
                   VALUES (:customer_id, :customer_name, :character_class, :character_species, :character_level)
                   RETURNING id"""
            ),
            {
                "customer_id": new_cart.customer_id,
                "customer_name": new_cart.customer_name,
                "character_class": new_cart.character_class,
                "character_species": new_cart.character_species,
                "character_level": new_cart.level,
            },
        ).one()
        cart_id = result.id

    return CartCreateResponse(cart_id=cart_id)


class CartItem(BaseModel):
    quantity: int = Field(ge=1, description="Quantity must be at least 1")


@router.post("/{cart_id}/items/{item_sku}", status_code=status.HTTP_204_NO_CONTENT)
def set_item_quantity(cart_id: int, item_sku: str, cart_item: CartItem):
    with db.engine.begin() as connection:
        # Check if cart exists
        cart_check = connection.execute(
            sqlalchemy.text("SELECT id FROM carts WHERE id = :cart_id"),
            {"cart_id": cart_id},
        ).fetchone()

        if not cart_check:
            raise HTTPException(status_code=404, detail="Cart not found")

        # Get potion_id from SKU
        potion_check = connection.execute(
            sqlalchemy.text("SELECT id FROM potions WHERE sku = :sku"),
            {"sku": item_sku},
        ).fetchone()

        if not potion_check:
            raise HTTPException(status_code=404, detail="Potion not found")

        potion_id = potion_check.id

        # Check if item already in cart
        existing = connection.execute(
            sqlalchemy.text(
                "SELECT id FROM cart_items WHERE cart_id = :cart_id AND potion_id = :potion_id"
            ),
            {"cart_id": cart_id, "potion_id": potion_id},
        ).fetchone()

        if existing:
            # Update quantity
            connection.execute(
                sqlalchemy.text(
                    "UPDATE cart_items SET quantity = :quantity WHERE cart_id = :cart_id AND potion_id = :potion_id"
                ),
                {
                    "quantity": cart_item.quantity,
                    "cart_id": cart_id,
                    "potion_id": potion_id,
                },
            )
        else:
            # Insert new item
            connection.execute(
                sqlalchemy.text(
                    "INSERT INTO cart_items (cart_id, potion_id, quantity) VALUES (:cart_id, :potion_id, :quantity)"
                ),
                {
                    "cart_id": cart_id,
                    "potion_id": potion_id,
                    "quantity": cart_item.quantity,
                },
            )


class CheckoutResponse(BaseModel):
    total_potions_bought: int
    total_gold_paid: int


class CartCheckout(BaseModel):
    payment: str


@router.post("/{cart_id}/checkout", response_model=CheckoutResponse)
def checkout(cart_id: int, cart_checkout: CartCheckout):
    """
    Handles the checkout process for a specific cart.
    The call is idempotent based on cart_id.
    """
    request_id = f"checkout_{cart_id}"

    with db.engine.begin() as connection:
        # Check if this checkout has already been processed
        existing_request = connection.execute(
            sqlalchemy.text(
                "SELECT response FROM processed_requests WHERE request_id = :request_id"
            ),
            {"request_id": request_id},
        ).fetchone()

        if existing_request:
            # Already processed, return the stored response
            import json

            response_data = (
                existing_request.response
                if isinstance(existing_request.response, dict)
                else json.loads(existing_request.response)
            )
            return CheckoutResponse(**response_data)

        # Check if cart exists
        cart_check = connection.execute(
            sqlalchemy.text(
                """
                SELECT id, customer_id, customer_name, character_class, character_species, character_level
                FROM carts
                WHERE id = :cart_id
                """
            ),
            {"cart_id": cart_id},
        ).fetchone()

        if not cart_check:
            raise HTTPException(status_code=404, detail="Cart not found")

        # Get all items in cart with potion details
        cart_items = connection.execute(
            sqlalchemy.text(
                """SELECT ci.quantity, p.id, p.sku, p.price
                   FROM cart_items ci
                   JOIN potions p ON ci.potion_id = p.id
                   WHERE ci.cart_id = :cart_id"""
            ),
            {"cart_id": cart_id},
        ).fetchall()

        if not cart_items:
            raise HTTPException(status_code=400, detail="Cart is empty")

        total_potions_bought = 0
        total_gold_paid = 0

        # Calculate totals and verify bottled stock is available.
        for item in cart_items:
            quantity = item.quantity
            price = item.price
            potion_id = item.id

            # Get current quantity from ledger
            quantity_on_hand = (
                connection.execute(
                    sqlalchemy.text(
                        """SELECT COALESCE(SUM(change), 0) as qty FROM potion_ledger_entries
                       WHERE potion_id = :potion_id"""
                    ),
                    {"potion_id": potion_id},
                )
                .one()
                .qty
            )

            if quantity_on_hand < quantity:
                raise HTTPException(
                    status_code=400, detail="Not enough potion inventory"
                )

            total_potions_bought += quantity
            total_gold_paid += quantity * price

        # Get current hour and day of week
        time_info = connection.execute(
            sqlalchemy.text(
                """SELECT EXTRACT(hour FROM now()) as hour_of_day,
                          EXTRACT(isodow FROM now()) as day_of_week"""
            )
        ).one()

        # Persist the checkout as a historical order for reporting/analytics.
        order_row = connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO order_history
                    (customer_id, customer_name, character_class, character_species, character_level,
                     total_potions_bought, total_gold_paid, hour_of_day, day_of_week)
                VALUES
                    (:customer_id, :customer_name, :character_class, :character_species, :character_level,
                     :total_potions_bought, :total_gold_paid, :hour_of_day, :day_of_week)
                RETURNING id
                """
            ),
            {
                "customer_id": cart_check.customer_id,
                "customer_name": cart_check.customer_name,
                "character_class": cart_check.character_class,
                "character_species": cart_check.character_species,
                "character_level": cart_check.character_level,
                "total_potions_bought": total_potions_bought,
                "total_gold_paid": total_gold_paid,
                "hour_of_day": int(time_info.hour_of_day),
                "day_of_week": int(time_info.day_of_week),
            },
        ).one()
        order_id = order_row.id

        # Create a potion transaction for the sale
        potion_transaction = connection.execute(
            sqlalchemy.text(
                """INSERT INTO potion_transactions (description) 
                   VALUES (:description) 
                   RETURNING id"""
            ),
            {"description": f"Sold {total_potions_bought} potions in order {order_id}"},
        ).one()
        potion_transaction_id = potion_transaction.id

        # Create a gold transaction for the payment
        gold_transaction = connection.execute(
            sqlalchemy.text(
                """INSERT INTO gold_transactions (description) 
                   VALUES (:description) 
                   RETURNING id"""
            ),
            {"description": f"Received {total_gold_paid} gold in order {order_id}"},
        ).one()
        gold_transaction_id = gold_transaction.id

        # Decrement potion quantities using ledger and record order history items
        for item in cart_items:
            potion_id = item.id
            sku = item.sku
            quantity = item.quantity
            price = item.price

            # Add potion ledger entry (negative because we're selling)
            connection.execute(
                sqlalchemy.text(
                    """INSERT INTO potion_ledger_entries (potion_id, potion_transaction_id, change) 
                       VALUES (:potion_id, :transaction_id, :change)"""
                ),
                {
                    "potion_id": potion_id,
                    "transaction_id": potion_transaction_id,
                    "change": -quantity,
                },
            )

            connection.execute(
                sqlalchemy.text(
                    """
                    INSERT INTO order_history_items
                        (order_id, potion_id, potion_sku, quantity, unit_price, line_total)
                    VALUES
                        (:order_id, :potion_id, :potion_sku, :quantity, :unit_price, :line_total)
                    """
                ),
                {
                    "order_id": order_id,
                    "potion_id": potion_id,
                    "potion_sku": sku,
                    "quantity": quantity,
                    "unit_price": price,
                    "line_total": quantity * price,
                },
            )

        # Add gold ledger entry (positive because we're receiving gold)
        connection.execute(
            sqlalchemy.text(
                """INSERT INTO gold_ledger_entries (gold_transaction_id, change) 
                   VALUES (:transaction_id, :change)"""
            ),
            {"transaction_id": gold_transaction_id, "change": total_gold_paid},
        )

        # Delete cart items
        connection.execute(
            sqlalchemy.text("DELETE FROM cart_items WHERE cart_id = :cart_id"),
            {"cart_id": cart_id},
        )

        # Delete cart
        connection.execute(
            sqlalchemy.text("DELETE FROM carts WHERE id = :cart_id"),
            {"cart_id": cart_id},
        )

        # Store the processed request
        response_data = {
            "total_potions_bought": total_potions_bought,
            "total_gold_paid": total_gold_paid,
        }
        connection.execute(
            sqlalchemy.text(
                """INSERT INTO processed_requests (request_id, response) 
                   VALUES (:request_id, :response)"""
            ),
            {"request_id": request_id, "response": response_data},
        )

    return CheckoutResponse(
        total_potions_bought=total_potions_bought, total_gold_paid=total_gold_paid
    )
