# Potion Shop Strategy

The strategy is now to use Supabase views as the source of truth for decision-making. The views give a clean, queryable dashboard for demand, customers, barrel pricing, and hourly activity.

## What To Optimize

1. Prioritize potions that show strong sales in `v_sales_per_potion_by_hour`.
- This tells you which specific potions move during which hours.
- Use it to keep stock and brewing focused on the winners.

2. Prefer barrel offers with the best `cost_per_ml` in `v_barrel_offers`.
- This directly lowers your raw material cost.
- Favor offers that also match the liquid colors needed by your top-selling potions.

3. Match potion supply to the most valuable customer segments in `v_customer_potion_demand`.
- Look for the class, species, and level combinations that buy the highest quantities and spend the most gold.
- Keep those potions stocked and available.

4. Use `v_sales_by_hour_summary` to find peak demand windows.
- That view shows the busiest hours overall.
- Use it to schedule inventory, pricing, or brewing focus around the busiest periods.

## Decision Rule

- If a potion is in the top demand groups and also sells during peak hours, keep it available.
- If a barrel offer has a low `cost_per_ml` and supports high-demand potion colors, buy it.
- If a potion does not appear in the demand or hour summaries, deprioritize it.

## Goal

The goal is to maximize profit by making the Supabase views the operational dashboard for purchasing and brewing decisions.
