-- Échoue si une serie avec moins de 12 points à fuité dans fact_food_prices_eligible
SELECT market_key, commodity_id, pricetype, COUNT(*) AS nb_points
FROM {{ ref('fact_food_prices_eligible') }}
GROUP BY market_key, commodity_id, pricetype
HAVING COUNT(*) < 12 