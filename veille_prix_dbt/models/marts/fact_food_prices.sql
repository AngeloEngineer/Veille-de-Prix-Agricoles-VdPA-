SELECT
  id,
  country_iso3 || '-' || market_id::TEXT AS market_key,
  commodity_id,
  price_date,
  pricetype,
  currency,
  price,
  usdprice
FROM {{ ref('int_food_prices_filtered') }}