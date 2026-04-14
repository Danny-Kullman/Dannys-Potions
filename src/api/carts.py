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
                {"quantity": cart_item.quantity, "cart_id": cart_id, "potion_id": potion_id},
            )
        else:
            # Insert new item
            connection.execute(
                sqlalchemy.text(
                    "INSERT INTO cart_items (cart_id, potion_id, quantity) VALUES (:cart_id, :potion_id, :quantity)"
                ),
                {"cart_id": cart_id, "potion_id": potion_id, "quantity": cart_item.quantity},
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
    """
    with db.engine.begin() as connection:
        # Check if cart exists
        cart_check = connection.execute(
            sqlalchemy.text("SELECT id FROM carts WHERE id = :cart_id"),
            {"cart_id": cart_id},
        ).fetchone()
        
        if not cart_check:
            raise HTTPException(status_code=404, detail="Cart not found")
        
        # Get all items in cart with potion details
        cart_items = connection.execute(
            sqlalchemy.text(
                """SELECT ci.quantity, p.id, p.price, p.red_ml, p.green_ml, p.blue_ml, p.dark_ml
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
        total_red_ml = 0
        total_green_ml = 0
        total_blue_ml = 0
        total_dark_ml = 0
        
        # Calculate totals and check inventory
        for item in cart_items:
            quantity = item.quantity
            price = item.price
            total_potions_bought += quantity
            total_gold_paid += quantity * price
            total_red_ml += item.red_ml * quantity
            total_green_ml += item.green_ml * quantity
            total_blue_ml += item.blue_ml * quantity
            total_dark_ml += item.dark_ml * quantity
        
        # Check global inventory has enough ml
        inventory = connection.execute(
            sqlalchemy.text(
                "SELECT red_ml, green_ml, blue_ml, dark_ml FROM global_inventory"
            )
        ).one()
        
        if (inventory.red_ml < total_red_ml or 
            inventory.green_ml < total_green_ml or
            inventory.blue_ml < total_blue_ml or
            inventory.dark_ml < total_dark_ml):
            raise HTTPException(status_code=400, detail="Not enough potions in inventory")
        
        # Decrement potion quantities
        for item in cart_items:
            connection.execute(
                sqlalchemy.text(
                    "UPDATE potions SET quantity_on_hand = quantity_on_hand - :quantity WHERE id = :potion_id"
                ),
                {"quantity": item.quantity, "potion_id": item.id},
            )
        
        # Update global inventory: add gold, decrement ml
        connection.execute(
            sqlalchemy.text(
                """UPDATE global_inventory SET 
                   gold = gold + :total_gold_paid,
                   red_ml = red_ml - :total_red_ml,
                   green_ml = green_ml - :total_green_ml,
                   blue_ml = blue_ml - :total_blue_ml,
                   dark_ml = dark_ml - :total_dark_ml"""
            ),
            {
                "total_gold_paid": total_gold_paid,
                "total_red_ml": total_red_ml,
                "total_green_ml": total_green_ml,
                "total_blue_ml": total_blue_ml,
                "total_dark_ml": total_dark_ml,
            },
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
    
    return CheckoutResponse(
        total_potions_bought=total_potions_bought, total_gold_paid=total_gold_paid
    )
