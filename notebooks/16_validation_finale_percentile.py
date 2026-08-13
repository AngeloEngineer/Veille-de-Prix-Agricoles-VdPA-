"""
Phase 6 — Script de validation finale avant matérialisation dbt.

DÉCISIONS PRISES SUITE AUX INVESTIGATIONS (scripts 14 et 15) :
─────────────────────────────────────────────────────────────────
1. PAS de clip/trimming des pct_change avant calcul des percentiles.
   RAISON : Les groupes "suspects" contiennent du signal économique réel (saisonnalité
   forte produits frais Nigeria, crise NGN 2022 sur lait en poudre). Clipper serait
   masquer du signal réel. Les artéfacts manifestes (ex. cowpeas brown NGN 9211%)
   seront eux-mêmes flagués comme anomalies — c'est exactement le bon comportement.

2. Les 3 groupes < 30 points (commodity_id 120 Wholesale=11, 484 Wholesale=13, 52 Wholesale=29)
   sont EXCLUS du calcul de percentile (seuil min_n=30 dans le script 14).
   RAISON : un percentile 1%/99% sur <30 points = un seul point détermine le seuil → non fiable.
   Ces séries sont conservées dans fact_food_prices_eligible mais ne seront pas flaggées.

3. Groupement par (commodity_id + pricetype) confirmé comme correct.
   RAISON : 67 groupes de taille médiane 1237 points → très confortable pour des percentiles stables.

4. Signal = pct_change mois/mois sur `price` (devise locale).
   RAISON : usdprice intègre la volatilité du taux de change, surtout sur le NGN,
   ce qui créerait des faux positifs liés à la dévaluation monétaire, pas aux prix agricoles.

5. TAUX ATTENDU ≈ 1.99% (mesuré empiriquement en script 14) → conforme à l'objectif.

VALIDATION FINALE DANS CE SCRIPT :
─────────────────────────────────
- Reproduire exactement le calcul qui sera dans dbt (SQL-compatible)
- Vérifier la cohérence des anomalies par pays, commodité, saison
- Vérifier qu'on ne masque pas une "hecatombe" derrière un taux global bas
  (i.e. un pays ou une commodité à 20%+ qui tire la moyenne vers 2%)
- Produire un export utilisable pour le prochain script dbt
"""

import psycopg2
import pandas as pd
import numpy as np

PG_DSN = "dbname=veille_prix_agricoles"
MIN_N_POUR_PERCENTILE = 30  # cohérent avec la décision actée ci-dessus

print("=" * 60)
print("PHASE 6 — VALIDATION FINALE DE L'APPROCHE PERCENTILE")
print("=" * 60)

conn = psycopg2.connect(PG_DSN)
df = pd.read_sql("""
    SELECT market_key, commodity_id, pricetype, price_date, price
    FROM dbt_dev.fact_food_prices_eligible
    ORDER BY market_key, commodity_id, pricetype, price_date
""", conn)

# On récupère aussi les noms de commodités pour la validation qualitative
commo = pd.read_sql("SELECT commodity_id, commodity, category FROM dbt_dev.dim_commodities", conn)
conn.close()

df["price_date"] = pd.to_datetime(df["price_date"])
df["pct_change"] = df.groupby(["market_key","commodity_id","pricetype"])["price"].pct_change()

# Points évaluables (exclure premier point, infinis)
df_eval = df[df["pct_change"].notna() & ~np.isinf(df["pct_change"])].copy()

# ── Calcul des seuils percentile par groupe (approche directe, sans apply) ────
rows = []
for (cid, ptype), grp in df_eval.groupby(["commodity_id", "pricetype"]):
    vals = grp["pct_change"].values
    n = len(vals)
    if n < MIN_N_POUR_PERCENTILE:
        rows.append({"commodity_id": cid, "pricetype": ptype,
                     "p01": np.nan, "p99": np.nan, "n_group": n, "has_threshold": False})
    else:
        rows.append({"commodity_id": cid, "pricetype": ptype,
                     "p01": float(np.percentile(vals, 1)),
                     "p99": float(np.percentile(vals, 99)),
                     "n_group": n, "has_threshold": True})
thresholds = pd.DataFrame(rows)

n_avec_seuil = int(thresholds["has_threshold"].sum())
n_sans_seuil = int((~thresholds["has_threshold"]).sum())
print(f"\nGroupes avec seuil calculable (n >= {MIN_N_POUR_PERCENTILE}) : {n_avec_seuil}")
print(f"Groupes trop petits, sans seuil : {n_sans_seuil}")

# ── Jointure et flaggage ───────────────────────────────────────────────────────
df_scored = df_eval.merge(
    thresholds[["commodity_id","pricetype","p01","p99","has_threshold"]],
    on=["commodity_id","pricetype"], how="left"
)

df_scored_eligible = df_scored[df_scored["has_threshold"] == True].copy()
df_scored_eligible["is_anomaly"] = (
    (df_scored_eligible["pct_change"] < df_scored_eligible["p01"]) |
    (df_scored_eligible["pct_change"] > df_scored_eligible["p99"])
)
df_scored_eligible["anomaly_direction"] = np.where(
    df_scored_eligible["pct_change"] < df_scored_eligible["p01"], "baisse",
    np.where(df_scored_eligible["pct_change"] > df_scored_eligible["p99"], "hausse", "normal")
)

n_eval = len(df_scored_eligible)
n_anom = df_scored_eligible["is_anomaly"].sum()
print(f"\n{'='*50}")
print(f"RÉSULTAT GLOBAL :")
print(f"  Points évaluables : {n_eval:,}")
print(f"  Anomalies totales : {n_anom:,}")
print(f"  Taux global       : {n_anom/n_eval*100:.2f}%")
print(f"  Hausse            : {(df_scored_eligible['anomaly_direction']=='hausse').sum():,} ({(df_scored_eligible['anomaly_direction']=='hausse').mean()*100:.2f}%)")
print(f"  Baisse            : {(df_scored_eligible['anomaly_direction']=='baisse').sum():,} ({(df_scored_eligible['anomaly_direction']=='baisse').mean()*100:.2f}%)")

# ── Contrôle : y a-t-il une "écatombe" cachée derrière le 2% global ? ─────────
print(f"\n{'='*50}")
print("CONTRÔLE ANTI-ÉCATOMBE : Taux par pays")
df_scored_eligible["country_iso3"] = df_scored_eligible["market_key"].str[:3]
by_country = df_scored_eligible.groupby("country_iso3").agg(
    n_eval=("is_anomaly","count"),
    n_anom=("is_anomaly","sum")
)
by_country["taux_pct"] = (by_country["n_anom"] / by_country["n_eval"] * 100).round(2)
print(by_country.to_string())
ecatombe_pays = by_country[by_country["taux_pct"] > 10]
if len(ecatombe_pays) > 0:
    print(f"\n  ⚠️  ÉCATOMBE DÉTECTÉE sur : {ecatombe_pays.index.tolist()}")
else:
    print(f"\n  ✅ Aucun pays avec taux > 10% — pas d'écatombe cachée.")

print(f"\n{'='*50}")
print("CONTRÔLE ANTI-ÉCATOMBE : Taux par catégorie de commodité")
df_by_cat = df_scored_eligible.merge(commo, on="commodity_id", how="left")
by_cat = df_by_cat.groupby("category").agg(
    n_eval=("is_anomaly","count"),
    n_anom=("is_anomaly","sum")
)
by_cat["taux_pct"] = (by_cat["n_anom"] / by_cat["n_eval"] * 100).round(2)
print(by_cat.to_string())
ecatombe_cat = by_cat[by_cat["taux_pct"] > 10]
if len(ecatombe_cat) > 0:
    print(f"\n  ⚠️  ÉCATOMBE sur catégorie : {ecatombe_cat.index.tolist()}")
else:
    print(f"\n  ✅ Aucune catégorie avec taux > 10%.")

print(f"\n{'='*50}")
print("CONTRÔLE ANTI-ÉCATOMBE : Taux par commodité (top 10 et bottom 10)")
by_commo = df_by_cat.groupby(["commodity_id","commodity","pricetype"]).agg(
    n_eval=("is_anomaly","count"),
    n_anom=("is_anomaly","sum")
).reset_index()
by_commo["taux_pct"] = (by_commo["n_anom"] / by_commo["n_eval"] * 100).round(2)
by_commo = by_commo.sort_values("taux_pct", ascending=False)
print(f"\n  Top 10 commodités les plus anomales :")
print(by_commo.head(10)[["commodity","pricetype","n_eval","n_anom","taux_pct"]].to_string(index=False))
print(f"\n  Bottom 10 commodités les moins anomales :")
print(by_commo.tail(10)[["commodity","pricetype","n_eval","n_anom","taux_pct"]].to_string(index=False))

# Alerte si commodité > 15%
ecatombe_commo = by_commo[by_commo["taux_pct"] > 15]
if len(ecatombe_commo) > 0:
    print(f"\n  ⚠️  ÉCATOMBE sur commodité : {ecatombe_commo[['commodity','pricetype','taux_pct']].values.tolist()}")
else:
    print(f"\n  ✅ Aucune commodité avec taux > 15%.")

print(f"\n{'='*50}")
print("CONTRÔLE ANTI-ÉCATOMBE : Distribution temporelle (anomalies par année)")
df_scored_eligible["annee"] = df_scored_eligible["price_date"].dt.year
by_year = df_scored_eligible.groupby("annee").agg(
    n_eval=("is_anomaly","count"),
    n_anom=("is_anomaly","sum")
)
by_year["taux_pct"] = (by_year["n_anom"] / by_year["n_eval"] * 100).round(2)
print(by_year.to_string())
print(f"\n  → Les années avec taux > 5% pourraient indiquer des chocs réels")
print(f"    (ex. crise NGN 2022, COVID 2020, etc.) — pas un bug.")

print(f"\n{'='*50}")
print("VALIDATION QUALITATIVE : 5 anomalies hausse les plus sévères")
top_hausse = (
    df_scored_eligible[df_scored_eligible["anomaly_direction"]=="hausse"]
    .merge(commo, on="commodity_id")
    .assign(ecart_vs_seuil=lambda x: x["pct_change"] - x["p99"])
    .sort_values("ecart_vs_seuil", ascending=False)
    .head(5)[["market_key","commodity","pricetype","price_date","price","pct_change","p99","ecart_vs_seuil"]]
)
print(top_hausse.to_string(index=False))

print(f"\nVALIDATION QUALITATIVE : 5 anomalies baisse les plus sévères")
top_baisse = (
    df_scored_eligible[df_scored_eligible["anomaly_direction"]=="baisse"]
    .merge(commo, on="commodity_id")
    .assign(ecart_vs_seuil=lambda x: x["pct_change"] - x["p01"])
    .sort_values("ecart_vs_seuil")
    .head(5)[["market_key","commodity","pricetype","price_date","price","pct_change","p01","ecart_vs_seuil"]]
)
print(top_baisse.to_string(index=False))

# ── Export des seuils — ce seront les valeurs embarquées dans dbt ──────────────
thresholds_export = thresholds[thresholds["has_threshold"]].copy()
thresholds_export = thresholds_export.rename(columns={"n_group":"n_points_groupe"})
thresholds_export.to_csv(
    "/home/broly/Mes_Projets/Veille_Prix_Agricoles/notebooks/phase6_seuils_percentile.csv",
    index=False
)
print(f"\n\n  → Seuils exportés dans phase6_seuils_percentile.csv")

print("\n" + "=" * 60)
print("VALIDATION TERMINÉE — FEUX VERTS POUR LE MODÈLE DBT")
print("=" * 60)
