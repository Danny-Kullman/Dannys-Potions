# Potion Shop Metrics Views

### `v_sales_per_potion_by_hour`
Sales per potion by hour, grouped by potion and hour.

Columns include:
- `hour_of_day`
- `potion_id`
- `potion_sku`
- `potion_name`
- `quantity_sold`
- `gold_spent`
- `order_count`

SQL:

```sql
SELECT *
FROM v_sales_per_potion_by_hour
ORDER BY potion_sku, hour_of_day;
```

### `v_barrel_offers`
All barrel offers, when they were offered, their liquid mix, and their cost per ml.

Columns include:
- `id`
- `sku`
- `offered_at`
- `ml_per_barrel`
- `potion_type_red`
- `potion_type_green`
- `potion_type_blue`
- `potion_type_dark`
- `price`
- `quantity`
- `cost_per_ml`
- `composition_total`

SQL:

```sql
SELECT *
FROM v_barrel_offers
ORDER BY offered_at DESC;
```

### `v_customer_potion_demand`
Who is buying what, grouped by class, species, and level.

Columns include:
- `character_class`
- `character_species`
- `character_level`
- `customer_segment`
- `potion_id`
- `potion_sku`
- `potion_name`
- `quantity_sold`
- `gold_spent`
- `order_count`

SQL:

```sql
SELECT *
FROM v_customer_potion_demand
ORDER BY quantity_sold DESC, gold_spent DESC;
```

### `v_sales_by_hour_summary`
An overall hourly demand summary that adds a fourth view beyond the required three.

Columns include:
- `hour_of_day`
- `order_count`
- `total_potions_sold`
- `total_gold_spent`
- `unique_potions_sold`

SQL:

```sql
SELECT *
FROM v_sales_by_hour_summary
ORDER BY hour_of_day;
```
