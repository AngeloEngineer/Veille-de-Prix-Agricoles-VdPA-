/*
Sous ensemble fiable des prix, pour la detection d'anaomalies:
Pour ceux faire; deux règles metier explicites, décidées et documentées:
   1. priceflag = 'actual' uniquement (Dans le 8e script python on avait fait une investigation sur 'aggregate' et 'actual,aggregate
   qui sont des valeurs calculées/composites, pas des observations de marché fiables)

   2. category != 'non-food', je garde la category 'non-food' pour un futur usage : "coût de la vie", ici le thème c'est principalement
   la veille de prix agricoles donc on conserve cette categorie dans la couche staging
*/
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
  usdprice
FROM {{ ref('stg_food_prices') }}
WHERE priceflag = 'actual' AND category != 'non-food'