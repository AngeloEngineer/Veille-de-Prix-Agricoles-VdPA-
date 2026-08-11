-- Point d'entrée dbt unique vers le socle Postgres
-- Renommage/sélection de colonnes uniquement, aucune règle métier

SELECT
  id,
  country_iso3,
  price_date,
  admin1,
  admin2,
  market,
  market_id,
  latitude,
  longitude,
  category,
  commodity,
  commodity_id,
  unit,
  priceflag,
  pricetype,
  currency,
  price,
  usdprice,
  source_dataset,
  source_url,
  ingested_at
FROM {{ source('staging_postgres', 'stg_food_prices') }}
