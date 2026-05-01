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


def create_catalog() -> List[CatalogItem]:
    with db.engine.begin() as connection:
        result = connection.execute(
            sqlalchemy.text(
                """SELECT p.sku, p.name, p.price,
                   COALESCE(SUM(pl.change), 0) as quantity_on_hand,
                   p.red_ml, p.green_ml, p.blue_ml, p.dark_ml
                FROM potions p
                LEFT JOIN potion_ledger_entries pl ON p.id = pl.potion_id
                GROUP BY p.id, p.sku, p.name, p.price, p.red_ml, p.green_ml, p.blue_ml, p.dark_ml
                HAVING COALESCE(SUM(pl.change), 0) > 0
                ORDER BY p.price ASC"""
            )
        ).fetchall()

        catalog = []
        for row in result:
            catalog.append(
                CatalogItem(
                    sku=row.sku,
                    name=row.name,
                    quantity=row.quantity_on_hand,
                    price=row.price,
                    potion_type=[
                        row.red_ml,
                        row.green_ml,
                        row.blue_ml,
                        row.dark_ml,
                    ],
                )
            )
        return catalog


@router.get("/catalog/", tags=["catalog"], response_model=List[CatalogItem])
def get_catalog() -> List[CatalogItem]:
    """
    Retrieves the catalog of items. Each unique item combination should have only a single price.
    You can have at most 6 potion SKUs offered in your catalog at one time.
    """
    return create_catalog()
