-- Échoue si une ligne 'aggregate' ou 'non-food' fuite dans le modèle intermédiaire
SELECT *
FROM {{ ref('int_food_prices_filtered') }}
WHERE priceflag != 'actual' OR category = 'non-food'