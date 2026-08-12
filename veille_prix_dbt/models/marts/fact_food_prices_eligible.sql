/*Sous ensemble de fact_food_prices restreint aux séries éligibles c'est à dire +12 points
Ca sera la base directe pour le calcul de médiane mobile/ Z-score*/
SELECT f.*
FROM {{ ref('fact_food_prices') }} f 
INNER JOIN {{ ref('dim_series_eligibility') }} e 
  ON f.market_key = e.market_key
  AND f.commodity_id = e.commodity_id
  AND f.pricetype = e.pricetype
WHERE e.is_eligible = true