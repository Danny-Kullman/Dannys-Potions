from src.api.bottler import create_bottle_plan


def test_bottle_red_potions() -> None:
    red_ml: int = 100
    green_ml: int = 0
    blue_ml: int = 0
    dark_ml: int = 0
    maximum_potion_capacity: int = 1000
    
    # Test with the standard recipes from the potions table seed
    recipes = [
        (100, 0, 0, 0),    # Red
        (0, 100, 0, 0),    # Green
        (0, 0, 100, 0),    # Blue
        (0, 0, 0, 100),    # Dark
        (50, 0, 50, 0),    # Purple
    ]

    result = create_bottle_plan(
        recipes=recipes,
        red_ml=red_ml,
        green_ml=green_ml,
        blue_ml=blue_ml,
        dark_ml=dark_ml,
        maximum_potion_capacity=maximum_potion_capacity,
    )

    assert len(result) == 1
    assert result[0].potion_type == [100, 0, 0, 0]
    assert result[0].quantity == 1
