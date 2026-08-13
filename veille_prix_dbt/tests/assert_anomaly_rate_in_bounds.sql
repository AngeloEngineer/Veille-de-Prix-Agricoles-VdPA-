-- assert_anomaly_rate_in_bounds
-- ─────────────────────────────────────────────────────────────────────────────
-- Garde-fou de non-régression sur le taux global d'anomalies.
--
-- Ce test ÉCHOUE (retourne des lignes) si :
--   • Le taux d'anomalies évaluées est < 0,5% → trop peu, le modèle serait aveugle
--   • Le taux d'anomalies évaluées est > 5,0% → trop élevé, retour au bruit
--
-- "Évaluées" = points avec pct_change non NULL ET groupe avec seuil calculable
-- (n_group >= 30) — ceux avec anomaly_direction = 'non_evalue' sont exclus.
--
-- RÉSULTAT VALIDÉ ATTENDU : ≈ 1.99% (calculé en script 16_validation_finale_percentile.py)
--
-- BORNE INFÉRIEURE 0.5% : si le modèle dbt change et ne détecte plus rien,
--   ce test le signale immédiatement.
-- BORNE SUPÉRIEURE 5.0% : marge confortable au-dessus du 2% attendu,
--   pour absorber d'éventuels nouveaux pays ou nouvelles commodités sans faux échec,
--   tout en bloquant une dérive majeure (retour aux 7-10% des approches précédentes).
--
-- INSTRUCTION DE LECTURE DU RÉSULTAT :
--   • 0 lignes retournées → test PASS (comportement normal dbt)
--   • 1 ligne retournée  → test FAIL, lire anomaly_rate_pct pour diagnostiquer

WITH counts AS (
    SELECT
        COUNT(*) FILTER (WHERE anomaly_direction != 'non_evalue') AS n_evalues,
        COUNT(*) FILTER (WHERE is_anomaly = TRUE)                 AS n_anomalies
    FROM {{ ref('fact_food_prices_anomalies') }}
),
rate AS (
    SELECT
        n_evalues,
        n_anomalies,
        ROUND(
            CAST(n_anomalies AS NUMERIC) / NULLIF(n_evalues, 0) * 100,
            4
        ) AS anomaly_rate_pct
    FROM counts
)
SELECT
    n_evalues,
    n_anomalies,
    anomaly_rate_pct,
    'FAIL: taux hors bornes [0.5%, 5.0%]' AS raison_echec
FROM rate
WHERE anomaly_rate_pct < 0.5
   OR anomaly_rate_pct > 5.0
   OR n_evalues < 100000  -- protection supplémentaire : si la table est quasi vide, c'est un bug
