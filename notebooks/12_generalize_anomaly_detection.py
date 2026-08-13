"""
Généralisation de la détection d'anomalies aux 2616 séries éligibles,
+ test de saisonnalité par mois calendaire

On veut verifier l'hyothèse selon laquelle le taux d'anomalies est uniforme sur 
l'année, ou si le taux d'anomalies est uniforme sur l'année, ou concentré sur 
Juin-septembre
"""
import numpy as np
import pandas as pd
import psycopg2

PG_DSN = "dbname=veille_prix_agricoles"
FENETRE=12
Z_THRESHOLD = 3.5

conn = psycopg2.connect(PG_DSN)
df = pd.read_sql(
    """
SELECT market_key, commodity_id, pricetype, price_date, price
FROM dbt_dev.fact_food_prices_eligible
ORDER BY market_key, commodity_id, pricetype, price_date
""",
conn)
conn.close()

df["price_date"] = pd.to_datetime(df["price_date"])

def compute_anomalies(group: pd.DataFrame) -> pd.DataFrame:
    group = group.sort_values("price_date").copy()
    group["rolling_median"] = group["price"].rolling(window=FENETRE, min_periods=FENETRE).median()
    group["rolling_mad"] = (
    group["price"]
    .rolling(window=FENETRE, min_periods=FENETRE)
    .apply(lambda x: np.median(np.abs(x - np.median(x))), raw=True)
)
    group["modified_z"] = 0.6745*(group["price"]-group["rolling_median"]) / group["rolling_mad"].replace(0, np.nan)
    group["is_anomaly"] = group["modified_z"].abs() > Z_THRESHOLD
    return group

nb_series = df.groupby(["market_key", "commodity_id", "pricetype"]).ngroups
print(f"CALCUL EN COURS SUR {nb_series} SÉRIES ...")

result = df.groupby(["market_key", "commodity_id", "pricetype"], group_keys=False).apply(compute_anomalies)

evaluable = result[result["modified_z"].notna()].copy()
print(f"\nPoints évaluables (fenêtre pleine): {len(evaluable)} / {len(result)}")
print(f"Anomalies détectées : {evaluable["is_anomaly"].sum()} ({evaluable["is_anomaly"].mean()*100:.2f}%)")

# --- Test de saisonnalité ---
evaluable["month"] = evaluable["price_date"].dt.month
seasonality = evaluable.groupby("month").agg(
    nb_points = ("modified_z", "count"),
    taux_anomalie_pct = ("is_anomaly", lambda s: round(s.mean()*100, 2)),
    z_moyen_abs=("modified_z", lambda s: round(s.abs().mean(), 3)),
)

print("\n --- Taux d'anomalie et |Z| moyen par mois calendaire ---")
print(seasonality)

result.to_csv("anomaly_detection_full.csv", index=False)
print("\nRésultat complet sauvegardé : anomaly_detection_full.csv")
