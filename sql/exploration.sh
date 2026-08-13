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

psql -d veille_prix_agricoles -c "
SELECT is_eligible, COUNT(*) as nb_series
FROM dbt_dev.dim_series_eligibility
GROUP BY is_eligible;
"

# ─────────────────────────────────────────────────────────────────────────────
# PHASE 6 — Détection d'anomalies par percentile P01/P99
# (scripts exécutés lors de la session de clôture — août 2026)
# ─────────────────────────────────────────────────────────────────────────────

# Inventaire complet des fichiers Python et SQL du projet avant de commencer
find /home/broly/Mes_Projets/Veille_Prix_Agricoles -name "*.py" | grep -v ".venv" | sort
find /home/broly/Mes_Projets/Veille_Prix_Agricoles -name "*.py" -o -name "*.sql" | grep -v ".venv" | sort

# Listage des dossiers clés
ls /home/broly/Mes_Projets/Veille_Prix_Agricoles/notebooks/
ls /home/broly/Mes_Projets/Veille_Prix_Agricoles/src/
ls /home/broly/Mes_Projets/Veille_Prix_Agricoles/sql/
find /home/broly/Mes_Projets/Veille_Prix_Agricoles/veille_prix_dbt/models -name "*.sql" | sort

# Script 14 — Profilage pré-implémentation percentile
# Vérifie la distribution des pct_change, les groupes, et simule le taux attendu
python notebooks/14_profil_avant_percentile.py

# Script 15 — Investigation des groupes suspects (P01 < -80% ou P99 > +300%)
python notebooks/15_investigate_suspects.py

# Script 16 — Validation finale anti-écatombe (pays / catégorie / commodité / année)
python notebooks/16_validation_finale_percentile.py

# Compilation dbt du nouveau modèle (vérification SQL avant build)
cd /home/broly/Mes_Projets/Veille_Prix_Agricoles/veille_prix_dbt && \
  source ../.venv/bin/activate && \
  dbt compile --select fact_food_prices_anomalies

# Build dbt du seul modèle anomalies + ses tests
cd /home/broly/Mes_Projets/Veille_Prix_Agricoles/veille_prix_dbt && \
  source ../.venv/bin/activate && \
  dbt build --select fact_food_prices_anomalies+

# Build dbt complet (toutes les 8 couches + 49 tests)
cd /home/broly/Mes_Projets/Veille_Prix_Agricoles/veille_prix_dbt && \
  source ../.venv/bin/activate && \
  dbt build

# Vérification Git avant commit (règle non négociable — section 3.2 du Claude.md)
git status

# Vérification que les CSV sont bien ignorés
git check-ignore -v notebooks/*.csv

# Vérification du résultat en base après matérialisation
psql -d veille_prix_agricoles -c "
SELECT
  anomaly_direction,
  COUNT(*)                                          AS nb_points,
  ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 2) AS pct
FROM dbt_dev.fact_food_prices_anomalies
GROUP BY anomaly_direction
ORDER BY nb_points DESC;
"

# Taux global d'anomalies — doit être dans [0.5%, 5.0%] (sinon assert_anomaly_rate_in_bounds échoue)
psql -d veille_prix_agricoles -c "
SELECT
  COUNT(*) FILTER (WHERE anomaly_direction != 'non_evalue') AS n_evalues,
  COUNT(*) FILTER (WHERE is_anomaly = TRUE)                 AS n_anomalies,
  ROUND(
    COUNT(*) FILTER (WHERE is_anomaly = TRUE) * 100.0
    / NULLIF(COUNT(*) FILTER (WHERE anomaly_direction != 'non_evalue'), 0),
    2
  ) AS taux_anomalies_pct
FROM dbt_dev.fact_food_prices_anomalies;
"

# Répartition par pays
psql -d veille_prix_agricoles -c "
SELECT
  country_iso3,
  COUNT(*) FILTER (WHERE anomaly_direction != 'non_evalue') AS n_evalues,
  COUNT(*) FILTER (WHERE is_anomaly = TRUE)                 AS n_anomalies,
  ROUND(
    COUNT(*) FILTER (WHERE is_anomaly = TRUE) * 100.0
    / NULLIF(COUNT(*) FILTER (WHERE anomaly_direction != 'non_evalue'), 0),
    2
  ) AS taux_pct
FROM dbt_dev.fact_food_prices_anomalies
GROUP BY country_iso3
ORDER BY country_iso3;
"

# Top 10 anomalies hausse les plus sévères (pour validation qualitative)
psql -d veille_prix_agricoles -c "
SELECT
  a.market_key, c.commodity, a.pricetype,
  a.price_date, a.price, a.pct_change,
  a.threshold_p99, a.anomaly_severity
FROM dbt_dev.fact_food_prices_anomalies a
JOIN dbt_dev.dim_commodities c ON a.commodity_id = c.commodity_id
WHERE a.anomaly_direction = 'hausse'
ORDER BY a.anomaly_severity DESC
LIMIT 10;
"

# Commit de clôture Phase 6
# git add Claude.md notebooks/13_*.py notebooks/14_*.py notebooks/15_*.py \
#          notebooks/16_*.py \
#          veille_prix_dbt/models/marts/fact_food_prices_anomalies.sql \
#          veille_prix_dbt/models/marts/_anomalies.yml \
#          veille_prix_dbt/tests/assert_anomaly_rate_in_bounds.sql
# git commit -m "feat(phase6): détection d'anomalies par percentile P01/P99 — dbt build 49/49 PASS"