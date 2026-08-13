/*
  fact_food_prices_anomalies
  ─────────────────────────────────────────────────────────────────────────────
  PHASE 6 — Détection d'anomalies de prix agricoles.

  MÉTHODE : Percentile non-paramétrique par groupe (commodity_id + pricetype).
  ─────────────────────────────────────────────────────────────────────────────
  Logique :
    1. Calculer la variation mois/mois (pct_change) pour chaque point de série,
       en utilisant LAG() par série individuelle (market_key + commodity_id + pricetype).
    2. Calculer les percentiles 1% et 99% de la distribution de pct_change
       en regroupant par (commodity_id + pricetype) — groupes de ~1237 points
       en médiane, suffisant pour une estimation percentile stable.
    3. Flaguer comme anomalie tout point dont le pct_change dépasse l'un des seuils.
    4. Exclure les groupes avec < 30 points de variation évaluable (seuil non fiable).

  DÉCISIONS DE CONCEPTION (voir Claude.md section 4 et notebooks 14-16) :
  - Signal = price (devise locale), PAS usdprice → évite les faux positifs
    dus à la dévaluation NGN (qui ne reflète pas la volatilité agricole).
  - Pas de clip/trim des variations extrêmes → les chocs réels extrêmes (crise NGN
    2022 sur le lait en poudre, artéfacts de saisie détectés) doivent être flagués,
    pas masqués dans les seuils.
  - Groupement par commodité+type, pas par série individuelle → séries trop courtes
    pour un percentile individuel stable ; le groupe agrège toutes les séries d'une
    même denrée dans le même type de marché sur tous les pays.
  - Seuil min_n_group = 30 → les 3 groupes trop petits (n<30) sont exclus du flaggage
    mais leurs points restent présents avec is_anomaly = FALSE (pas NULL) pour
    ne pas créer de trous invisibles dans la table de faits.

  RÉSULTATS VALIDÉS (script 16_validation_finale_percentile.py) :
  - Taux global : 1.99% (cible 0.5-2% atteinte)
  - Par pays : BFA 1.07%, NER 1.72%, NGA 2.96%, SEN 1.70%, TGO 2.86%
  - Par catégorie : toutes entre 1.78% et 2.09% → pas d'écatombe cachée
  - Par commodité : max 4.17% sur un groupe de 48 points (Wheat Wholesale)
  - Distribution temporelle cohérente avec les chocs économiques documentés
    (1996, 2005, 2022 = années de crises connues)
*/

{{ config(materialized='table') }}

WITH

-- Étape 1 : variation mois/mois par série individuelle
variations AS (
    SELECT
        id,
        market_key,
        commodity_id,
        pricetype,
        price_date,
        price,
        usdprice,
        currency,
        LAG(price) OVER (
            PARTITION BY market_key, commodity_id, pricetype
            ORDER BY price_date
        ) AS price_prev,
        CASE
            WHEN LAG(price) OVER (
                PARTITION BY market_key, commodity_id, pricetype
                ORDER BY price_date
            ) IS NULL THEN NULL
            WHEN LAG(price) OVER (
                PARTITION BY market_key, commodity_id, pricetype
                ORDER BY price_date
            ) = 0 THEN NULL  -- division par zéro = exclure (0 observé en pratique : 0 cas)
            ELSE (price - LAG(price) OVER (
                PARTITION BY market_key, commodity_id, pricetype
                ORDER BY price_date
            )) / LAG(price) OVER (
                PARTITION BY market_key, commodity_id, pricetype
                ORDER BY price_date
            )
        END AS pct_change
    FROM {{ ref('fact_food_prices_eligible') }}
),

-- Étape 2 : taille de chaque groupe pour le filtre min_n_group
group_sizes AS (
    SELECT
        commodity_id,
        pricetype,
        COUNT(pct_change) AS n_group  -- COUNT exclut les NULLs (premiers points)
    FROM variations
    WHERE pct_change IS NOT NULL
    GROUP BY commodity_id, pricetype
),

-- Étape 3 : seuils percentile par groupe (uniquement si n_group >= 30)
group_thresholds AS (
    SELECT
        v.commodity_id,
        v.pricetype,
        PERCENTILE_CONT(0.01) WITHIN GROUP (ORDER BY v.pct_change) AS p01,
        PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY v.pct_change) AS p99,
        gs.n_group
    FROM variations v
    JOIN group_sizes gs
        ON v.commodity_id = gs.commodity_id
        AND v.pricetype = gs.pricetype
    WHERE v.pct_change IS NOT NULL
      AND gs.n_group >= 30  -- seuil de fiabilité du percentile
    GROUP BY v.commodity_id, v.pricetype, gs.n_group
),

-- Étape 4 : jointure et flaggage
scored AS (
    SELECT
        v.id,
        v.market_key,
        LEFT(v.market_key, 3)           AS country_iso3,
        v.commodity_id,
        v.pricetype,
        v.price_date,
        v.price,
        v.usdprice,
        v.currency,
        v.pct_change,
        t.p01                           AS threshold_p01,
        t.p99                           AS threshold_p99,
        t.n_group                       AS n_group_for_threshold,
        -- Flaggage anomalie
        CASE
            WHEN v.pct_change IS NULL THEN FALSE  -- premier point de série, non évaluable
            WHEN t.p01 IS NULL        THEN FALSE  -- groupe trop petit, pas de seuil
            WHEN v.pct_change < t.p01 THEN TRUE
            WHEN v.pct_change > t.p99 THEN TRUE
            ELSE FALSE
        END                             AS is_anomaly,
        -- Direction de l'anomalie
        CASE
            WHEN v.pct_change IS NULL OR t.p01 IS NULL THEN 'non_evalue'
            WHEN v.pct_change < t.p01 THEN 'baisse'
            WHEN v.pct_change > t.p99 THEN 'hausse'
            ELSE 'normal'
        END                             AS anomaly_direction,
        -- Sévérité relative : distance au seuil en unités de variation
        -- Positive = dépasse le seuil dans la direction de l'anomalie
        CASE
            WHEN v.pct_change IS NULL OR t.p01 IS NULL THEN NULL
            WHEN v.pct_change < t.p01 THEN v.pct_change - t.p01   -- négatif = baisse anormale
            WHEN v.pct_change > t.p99 THEN v.pct_change - t.p99   -- positif = hausse anormale
            ELSE 0.0
        END                             AS anomaly_severity
    FROM variations v
    LEFT JOIN group_thresholds t
        ON v.commodity_id = t.commodity_id
        AND v.pricetype = t.pricetype
)

SELECT * FROM scored
ORDER BY market_key, commodity_id, pricetype, price_date
