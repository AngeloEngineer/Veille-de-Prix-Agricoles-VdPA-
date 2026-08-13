"""
Détection sur variation mois/mois (%) au lieu du prix brut — test unique et décisif.
"""
import numpy as np
import pandas as pd
import psycopg2

PG_DSN = "dbname=veille_prix_agricoles"
WINDOW = 12
Z_THRESHOLD = 3.5

conn = psycopg2.connect(PG_DSN)
df = pd.read_sql("""
    select market_key, commodity_id, pricetype, price_date, price
    from dbt_dev.fact_food_prices_eligible
    order by market_key, commodity_id, pricetype, price_date
""", conn)
conn.close()
df["price_date"] = pd.to_datetime(df["price_date"])

def compute(group):
    group = group.sort_values("price_date").copy()
    group["pct_change"] = group["price"].pct_change()
    med = group["pct_change"].rolling(WINDOW, min_periods=WINDOW).median()
    mad = group["pct_change"].rolling(WINDOW, min_periods=WINDOW).apply(
        lambda x: np.median(np.abs(x - np.median(x))), raw=True
    )
    z = 0.6745 * (group["pct_change"] - med) / mad.replace(0, np.nan)
    group["z"] = z
    group["is_anomaly"] = z.abs() > Z_THRESHOLD
    return group

result = df.groupby(["market_key", "commodity_id", "pricetype"], group_keys=False).apply(compute)
evaluable = result[result["z"].notna()]
print(f"Points évaluables : {len(evaluable)}")
print(f"Anomalies : {evaluable['is_anomaly'].sum()} ({evaluable['is_anomaly'].mean()*100:.2f}%)")
result.to_csv("anomaly_pct_change.csv", index=False)