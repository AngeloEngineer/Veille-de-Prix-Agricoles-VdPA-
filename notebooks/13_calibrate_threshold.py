"""
trouver une combinaison (fenêtre, seuil) qui ramène 
le taux d'anomalies à quelque chose de plausible (0.5-2%, pas 10%).
"""
import numpy as np
import pandas as pd
import psycopg2

PG_DSN = "dbname=veille_prix_agricoles"

conn = psycopg2.connect(PG_DSN)
df= pd.read_sql(
       """
    SELECT market_key, commodity_id, pricetype, price_date, price
    FROM dbt_dev.fact_food_prices_eligible
    ORDER BY market_key, commodity_id, pricetype, price_date
       """,
conn)
conn.close()
df["price_date"] = pd.to_datetime(df["price_date"])

def compute(group, window, z_threshold):
    group = group.sort_values("price_date").copy()
    med = group["price"].rolling(window, min_periods=window).median()
    mad = group["price"].rolling(window, min_periods=window).apply(
        lambda x: np.median(np.abs(x - np.median(x))), raw=True
    )
    z = 0.6745*(group["price"]-med) / mad.replace(0, np.nan)
    return pd.Series({"n": z.notna().sum(), "anomalies": (z.abs() > z_threshold).sum()})

results = []
for window in [12, 18, 24]:
    for z_threshold in [3.5, 5, 6]:
        agg = df.groupby(["market_key", "commodity_id", "pricetype"]).apply(
            lambda g: compute(g, window, z_threshold)
        )
        n, anomalies = agg["n"].sum(), agg["anomalies"].sum()
        results.append({
            "fenetre": window, "seuil": z_threshold,
            "n_points": n, "anomalies": anomalies,
            "taux_pct": round(anomalies / n*100, 3),
        })
        print(results[-1])

pd.DataFrame(results).to_csv("calibration_results.csv", index=False)
