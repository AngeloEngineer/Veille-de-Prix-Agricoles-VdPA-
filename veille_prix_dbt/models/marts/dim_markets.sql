SELECT DISTINCT
  country_iso3 || '-' || market_id::TEXT AS market_key,
  country_iso3,
  market_id,
  market,
  admin1,
  admin2,
  latitude,
  longitude
FROM {{ ref('int_food_prices_filtered') }}