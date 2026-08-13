"""
Phase 6 — Profilage préalable avant implémentation percentile.

OBJECTIF : Avant d'écrire le modèle dbt, comprendre empiriquement :
  1. La distribution des variations mois/mois par groupe (commodity_id + pricetype)
  2. La taille réelle des groupes (besoin >= ~200 points pour un percentile stable)
  3. La présence de valeurs aberrantes techniques (pct_change = infini, NaN, -100%)
  4. Vérifier que les percentiles 1% / 99% détectent bien des chocs économiques réels,
     et non des artéfacts de données (zeroes, doublons, etc.)

Ceci suit la discipline du Claude.md section 9 :
"Profiler avant de concevoir. Chaque seuil, chaque règle de filtrage a été précédé
d'un script d'exploration sur les données réelles."
"""

import psycopg2
import pandas as pd
import numpy as np

PG_DSN = "dbname=veille_prix_agricoles"

print("=" * 60)
print("PHASE 6 — PROFILAGE AVANT IMPLÉMENTATION PERCENTILE")
print("=" * 60)

conn = psycopg2.connect(PG_DSN)

# ── 1. Charger fact_food_prices_eligible ──────────────────────────────────────
print("\n[1/6] Chargement de fact_food_prices_eligible ...")
df = pd.read_sql("""
    SELECT
        market_key, commodity_id, pricetype, price_date, price, usdprice
    FROM dbt_dev.fact_food_prices_eligible
    ORDER BY market_key, commodity_id, pricetype, price_date
""", conn)
conn.close()

df["price_date"] = pd.to_datetime(df["price_date"])
print(f"  → {len(df):,} lignes chargées, {df.groupby(['market_key','commodity_id','pricetype']).ngroups:,} séries")

# ── 2. Calculer variation mois/mois par série ─────────────────────────────────
print("\n[2/6] Calcul de la variation mois/mois (pct_change) par série ...")
df = df.sort_values(["market_key", "commodity_id", "pricetype", "price_date"])
df["pct_change"] = (
    df.groupby(["market_key", "commodity_id", "pricetype"])["price"]
    .pct_change()
)

# Diagnostics techniques : valeurs problématiques
n_total = len(df)
n_premier_point = df["pct_change"].isna().sum()  # 1er point de chaque série = NaN normal
n_inf = np.isinf(df["pct_change"]).sum()          # prix_t-1 = 0 → division par zéro
n_minus1 = (df["pct_change"] == -1.0).sum()       # prix_t = 0 → variation = -100%
n_evaluable = df["pct_change"].notna() & ~np.isinf(df["pct_change"])

print(f"\n  DIAGNOSTICS pct_change :")
print(f"  • Total lignes          : {n_total:,}")
print(f"  • NaN (1er point série) : {n_premier_point:,}  → attendus, un par série")
print(f"  • Infinis (prix_t-1=0) : {n_inf:,}  → artéfact technique, à exclure")
print(f"  • pct_change = -100%   : {n_minus1:,}  → prix tombe à 0, probable erreur saisie")
print(f"  • Évaluables nets       : {n_evaluable.sum():,}")

# ── 3. Profil des groupes (commodity_id + pricetype) ─────────────────────────
print("\n[3/6] Profil des groupes commodity_id + pricetype ...")
df_eval = df[n_evaluable].copy()

grp_sizes = (
    df_eval.groupby(["commodity_id", "pricetype"])["pct_change"]
    .count()
    .reset_index(name="nb_points_eval")
    .sort_values("nb_points_eval")
)

print(f"\n  Nombre de groupes (commodity + pricetype) : {len(grp_sizes)}")
print(f"\n  Distribution de la taille des groupes :")
print(grp_sizes["nb_points_eval"].describe(percentiles=[0.05, 0.25, 0.5, 0.75, 0.95]).round(0))
print(f"\n  Groupes avec < 50 points (percentile instable) : {(grp_sizes['nb_points_eval'] < 50).sum()}")
print(f"  Groupes avec >= 200 points (percentile fiable) : {(grp_sizes['nb_points_eval'] >= 200).sum()}")

print(f"\n  10 plus petits groupes :")
print(grp_sizes.head(10).to_string(index=False))

print(f"\n  10 plus grands groupes :")
print(grp_sizes.tail(10).to_string(index=False))

# ── 4. Distribution des percentiles 1/99 par groupe ──────────────────────────
print("\n[4/6] Calcul des seuils percentile 1% / 99% par groupe ...")

def compute_group_percentiles(group):
    pct_vals = group["pct_change"].dropna()
    pct_vals = pct_vals[~np.isinf(pct_vals)]
    if len(pct_vals) < 30:  # trop petit pour être fiable
        return pd.Series({
            "n": len(pct_vals), "p01": np.nan, "p99": np.nan,
            "median": np.nan, "p25": np.nan, "p75": np.nan
        })
    return pd.Series({
        "n": len(pct_vals),
        "p01": np.percentile(pct_vals, 1),
        "p99": np.percentile(pct_vals, 99),
        "median": np.percentile(pct_vals, 50),
        "p25": np.percentile(pct_vals, 25),
        "p75": np.percentile(pct_vals, 75),
    })

pct_profile = (
    df_eval.groupby(["commodity_id", "pricetype"])
    .apply(compute_group_percentiles, include_groups=False)
    .reset_index()
)

print(f"\n  Distribution des seuils P01 (variation minimale « normale ») :")
print(pct_profile["p01"].dropna().describe(percentiles=[0.05, 0.25, 0.5, 0.75, 0.95]).round(4))

print(f"\n  Distribution des seuils P99 (variation maximale « normale ») :")
print(pct_profile["p99"].dropna().describe(percentiles=[0.05, 0.25, 0.5, 0.75, 0.95]).round(4))

# Groupes où P01 < -80% ou P99 > 300% → suspects
suspects_bas = pct_profile[pct_profile["p01"].notna() & (pct_profile["p01"] < -0.80)]
suspects_haut = pct_profile[pct_profile["p99"].notna() & (pct_profile["p99"] > 3.0)]
print(f"\n  Groupes avec P01 < -80% (suspect, probable artéfact) : {len(suspects_bas)}")
if len(suspects_bas) > 0:
    print(suspects_bas[["commodity_id","pricetype","n","p01","p99"]].to_string(index=False))

print(f"\n  Groupes avec P99 > +300% (suspect, possible doublon ou choc extrême) : {len(suspects_haut)}")
if len(suspects_haut) > 0:
    print(suspects_haut[["commodity_id","pricetype","n","p01","p99"]].to_string(index=False))

# ── 5. Simulation du taux d'anomalies attendu ─────────────────────────────────
print("\n[5/6] Simulation — quel serait le taux d'anomalies avec P01/P99 ?")

# Joindre les seuils au df_eval
df_flagged = df_eval.merge(
    pct_profile[["commodity_id","pricetype","p01","p99"]],
    on=["commodity_id","pricetype"],
    how="left"
)

# Exclure les groupes sans seuil calculable
df_flagged = df_flagged[df_flagged["p01"].notna()].copy()
df_flagged["is_anomaly_pct"] = (
    (df_flagged["pct_change"] < df_flagged["p01"]) |
    (df_flagged["pct_change"] > df_flagged["p99"])
)

n_eval = len(df_flagged)
n_anom = df_flagged["is_anomaly_pct"].sum()
print(f"\n  Points évaluables (avec seuil calculable) : {n_eval:,}")
print(f"  Anomalies détectées                       : {n_anom:,}")
print(f"  Taux global                               : {n_anom/n_eval*100:.2f}%")
print(f"  (Attendu théorique ≈ 2,00% — écart acceptable si groupes homogènes)")

# Répartition par direction
anom_bas = (df_flagged["pct_change"] < df_flagged["p01"]).sum()
anom_haut = (df_flagged["pct_change"] > df_flagged["p99"]).sum()
print(f"\n  Anomalies baisse (< P01) : {anom_bas:,}  ({anom_bas/n_eval*100:.2f}%)")
print(f"  Anomalies hausse (> P99) : {anom_haut:,}  ({anom_haut/n_eval*100:.2f}%)")

# Répartition par pays
df_flagged["country_iso3"] = df_flagged["market_key"].str[:3]
by_country = df_flagged.groupby("country_iso3").agg(
    n_eval=("is_anomaly_pct","count"),
    n_anom=("is_anomaly_pct","sum")
)
by_country["taux_pct"] = (by_country["n_anom"] / by_country["n_eval"] * 100).round(2)
print(f"\n  Taux d'anomalies par pays :")
print(by_country.to_string())

# ── 6. Validation qualitative : inspecter 10 anomalies "hausse" récentes ──────
print("\n[6/6] Validation qualitative — 10 anomalies hausse récentes ...")
anom_sample = (
    df_flagged[df_flagged["pct_change"] > df_flagged["p99"]]
    .sort_values("price_date", ascending=False)
    .head(10)[["market_key","commodity_id","pricetype","price_date","price","pct_change","p99"]]
)
anom_sample["hausse_vs_seuil"] = (anom_sample["pct_change"] - anom_sample["p99"]).round(4)
print(anom_sample.to_string(index=False))

print("\n[6/6] 10 anomalies baisse récentes ...")
anom_sample_bas = (
    df_flagged[df_flagged["pct_change"] < df_flagged["p01"]]
    .sort_values("price_date", ascending=False)
    .head(10)[["market_key","commodity_id","pricetype","price_date","price","pct_change","p01"]]
)
anom_sample_bas["baisse_vs_seuil"] = (anom_sample_bas["pct_change"] - anom_sample_bas["p01"]).round(4)
print(anom_sample_bas.to_string(index=False))

print("\n" + "=" * 60)
print("PROFILAGE TERMINÉ — lire les résultats ci-dessus avant")
print("d'implémenter le modèle dbt fact_food_prices_anomalies.sql")
print("=" * 60)
