/*Cardinalité par série (marché x commodité x type de prix), et flag d'éligibilité
à la détection d'anomalies. Seuil = 12 points.*/

SELECT
  market_key,
  commodity_id,
  pricetype,
  COUNT(*) AS nb_points,
  MIN(price_date) AS premiere_observation,
  MAX(price_date) AS derniere_observation,
  (COUNT(*) >= 12) AS is_eligible
FROM {{ ref('fact_food_prices') }}
GROUP BY market_key, commodity_id, pricetype