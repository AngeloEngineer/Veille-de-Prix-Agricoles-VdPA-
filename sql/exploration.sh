#!/bin/bash

# Une détection d'anomalie statistique n'a de sens que si chaque série assez de points historiques
# Une série avec 3 observations ne permet aucun calcul fiable de médiane mobile ou d'écart-type
# On doit savoir combien de points on a réellement, par série, avant de choisir la méthode et son seuil minimal

#1.
psql -d veille_prix_agricoles -c "
SELECT
  market_key, commodity_id, pricetype,
  COUNT(*) AS nb_points,
  MIN(price_date) AS debut,
  MAX(price_date) AS fin
FROM dbt_dev.fact_food_prices
GROUP BY market_key, commodity_id, pricetype
ORDER BY nb_points ASC
LIMIT 15;
"

#2.
psql -d veille_prix_agricoles -c "
SELECT
  COUNT(*) AS nb_series,
  MIN(nb_points) AS min_points,
  PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY nb_points) AS p25,
  PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY nb_points) AS mediane,
  ROUND(AVG(nb_points), 1) AS moyenne,
  MAX(nb_points) AS max_points
FROM (
    SELECT market_key, commodity_id, pricetype, COUNT(*) AS nb_points
    FROM dbt_dev.fact_food_prices
    GROUP BY market_key, commodity_id, pricetype
) s ;
"
# Suite à la sortie de la commande 2.; un détail dans le top 15 casse le pattern général, et mérite d'être isolé avant de conclure quoi que ce soit
# SEN-443 — commodité 198, un seul point, daté du 2014-06-15. Toutes les autres lignes à nb_points=1 sont datées d'avril/mai/juin 2026
# Ce qui est cohérent avec des séries jeunes qui viennent tout juste de démarrer et vont naturellement s'enrichir avec le temps
# SEN-443 n'a rien à voir avec ça : une observation isolée vieille de 12 ans, sans aucun suivi ni avant ni après, n'est pas "une série immature"
# c'est plus probablement une anomalie de collecte ponctuelle

#Ce que nous allons doc faire maintenant c'est quantifier combien de séries à 1 point sont de vraies séries récentes
#contre combien sont des points isolés anciens

#3.
psql -d veille_prix_agricoles -c "
SELECT
  COUNT(*) FILTER (WHERE nb_points = 1 AND fin >= '2026-01-01') AS series_recentes_1pt,
  COUNT(*) FILTER (WHERE nb_points = 1 AND fin < '2025-01-01') AS series_orphelines_1pt,
  COUNT(*) FILTER (WHERE nb_points = 1) AS total_1pt
FROM (
    SELECT market_key, commodity_id, pricetype, COUNT(*) AS nb_points, MAX(price_date) AS fin
    FROM dbt_dev.fact_food_prices
    GROUP BY market_key, commodity_id, pricetype
) s;
"

#4. 
psql -d veille_prix_agricoles -c "
SELECT market_key, commodity_id, pricetype, MIN(price_date) AS date_unique
FROM dbt_dev.fact_food_prices
GROUP BY market_key, commodity_id, pricetype
HAVING COUNT(*) = 1 AND MAX(price_date) < '2025-01-01'
ORDER BY date_unique;
"

# La sortie de 4 affiche une vue de 95 lignes dispersées mais un vrai pattern saute aux yeux

# Un pattern "commodité large, un seul jour" : au 2009-01-15, 15 marchés différents du Niger rapportent tous la commodité 84 et jamais avant, jamais après
# Encore plus frappant au 2014-06-15 : une trentaine de marchés sénégalais rapportent tous la commodité 198, uniquement ce jour-là
# Cela ne peut pas etre des coincidences indépendantes
# ça ressemble à un suivi de commodité lancé à l'échelle nationale puis abandonné immédiatement

# Un second pattern "marché large, un seul jour"
# NGA-3073 - 7 commodités différentes, toutes datées du 2017-02-15, jamais avant ni après.
# Même chose pour SEN-1398 (4 commodités, 2012-03-15) et SEN-454/SEN-422/SEN-5234 (plusieurs commodités chacun, 2020-04-15 et 2020-12-15)
# Ici c'est l'inverse : un marché entier semble être entré dans le suivi une seule fois puis en être sorti, pas un problème de commodité, un problème de marché.

# MON INTERPRETATION EST DONC LA SUIVANTE: 
# ces 95 lignes ne sont probablement pas des erreurs de saisie aléatoires
# ce sont des événements de collecte (lancement/abandon de suivi pour un marché ou une commodité donnée)
# Ce qui se manifestent statistiquement comme des séries à 1 point
# Elles restent réelles, on ne les invente pas, mais elles ne sont structurellement pas exploitables pour une détection d'anomalie temporelle
# pas parce qu'elles sont fausses, mais parce qu'il n'y a rien à comparer dans le temps.

#confirmons par le chiffre plutôt que par l'œil combien de ces 95 lignes s'expliquent par ce clustering, et combien restent vraiment isolées sans aucun voisin.



#5.
psql -d veille_prix_agricoles -c "
SELECT date_unique, COUNT(*) AS nb_series_ce_jour
FROM (
    SELECT market_key, commodity_id, pricetype, MIN(price_date) AS date_unique
    FROM dbt_dev.fact_food_prices
    GROUP BY market_key, commodity_id, pricetype
    HAVING COUNT(*) = 1 AND MAX(price_date) < '2025-01-01'
) orphelines
GROUP BY date_unique
ORDER BY nb_series_ce_jour DESC;
"

# Les chiffres de la sortie de 4. tranchent la question de façon nette : 82 des 95 séries orphelines (86%) s'expliquent
# par seulement 8 dates de clustering (2014-06-15, 2009-01-15, 2020-04-15, 2020-12-15, 2017-02-15, 2012-03-15, 2022-11-15, 2021-06-15) 
# l'hypothèse "campagnes de suivi lancées puis arrêtées" est confirmée numériquement, pas juste visuellement. Il ne reste que 13 dates réellement isolées (nb_series_ce_jour = 1),
# aucun autre marché/commodité ne partageant leur date.

# Ce que nous allons faire là maintenant à cette étape, c'est d'aller matérialiser la règle d'éligibilité dans dbt

# Vérification complémentaire de la matérialisation complémentaire en plus du bdt build

#6. 
psql -d veille_prix_agricoles -c "
SELECT is_eligible, COUNT(*) as nb_series
FROM dbt_dev.dim_series_eligibility
GROUP BY is_eligible;
"