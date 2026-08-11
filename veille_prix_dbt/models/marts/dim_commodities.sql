SELECT DISTINCT
  commodity_id,
  commodity,
  category
FROM {{ ref('int_food_prices_filtered') }}