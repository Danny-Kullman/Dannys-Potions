from fastapi import APIRouter
from pydantic import BaseModel, Field
from typing import List, Annotated
import sqlalchemy
from src import database as db

router = APIRouter()


class CatalogItem(BaseModel):
    sku: Annotated[str, Field(pattern=r"^[a-zA-Z0-9_]{1,20}$")]
    name: str
    quantity: Annotated[int, Field(ge=1, le=10000)]
    price: Annotated[int, Field(ge=1, le=500)]
    potion_type: List[int] = Field(
        ...,
        min_length=4,
        max_length=4,
        description="Must contain exactly 4 elements: [r, g, b, d]",
    )


# Placeholder function, you will replace this with a database call
def create_catalog() -> List[CatalogItem]:
    with db.engine.begin() as connection:
        result = connection.execute(
            sqlalchemy.text(
                "SELECT red_potions, green_potions, blue_potions, dark_potions FROM global_inventory"
            )
        ).fetchone()
        red_potions = result.red_potions
        green_potions = result.green_potions
        blue_potions = result.blue_potions
        dark_potions = result.dark_potions

    catalog_items: List[CatalogItem] = []

    if red_potions > 0:
        catalog_items.append(
            CatalogItem(
                sku="red",
                name="red potion",
                quantity=red_potions,
                price=50,
                potion_type=[100, 0, 0, 0],
            )
        )

    if green_potions > 0:
        catalog_items.append(
            CatalogItem(
                sku="green",
                name="green potion",
                quantity=green_potions,
                price=50,
                potion_type=[0, 100, 0, 0],
            )
        )

    if blue_potions > 0:
        catalog_items.append(
            CatalogItem(
                sku="blue",
                name="blue potion",
                quantity=blue_potions,
                price=50,
                potion_type=[0, 0, 100, 0],
            )
        )

    if dark_potions > 0:
        catalog_items.append(
            CatalogItem(
                sku="dark",
                name="dark potion",
                quantity=dark_potions,
                price=50,
                potion_type=[0, 0, 0, 100],
            )
        )

    return catalog_items


@router.get("/catalog/", tags=["catalog"], response_model=List[CatalogItem])
def get_catalog() -> List[CatalogItem]:
    """
    Retrieves the catalog of items. Each unique item combination should have only a single price.
    You can have at most 6 potion SKUs offered in your catalog at one time.
    """
    return create_catalog()
