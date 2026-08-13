"""
Visualisation de la série de validation : prix, mediane mobile et anomalies détectées.
"""
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import psycopg2

PG_DSN = "dbname=veille_prix_agricoles"
FENETRE = 12
Z_THRESHOLD = 3.5

conn = psycopg2.connect(PG_DSN)
df = pd.read_sql(
    """
SELECT price_date, price
FROM dbt_dev.fact_food_prices_eligible
WHERE market_key = 'NER-602' AND commodity_id = 73 AND pricetype = 'Retail'
ORDER BY price_date
   """,
    conn,
)
conn.close()

df["price_date"] = pd.to_datetime(df["price_date"])
df["rolling_median"] = (
    df["price"].rolling(window=FENETRE, min_periods=FENETRE).median()
)

# Utilisation des fonctions NumPy sur l'array 'x'
df["rolling_mad"] = (
    df["price"]
    .rolling(window=FENETRE, min_periods=FENETRE)
    .apply(lambda x: np.median(np.abs(x - np.median(x))), raw=True)
)

# Calcul du Z-score modifié
df["modified_z"] = (
    0.6745
    * (df["price"] - df["rolling_median"])
    / df["rolling_mad"].replace(0, float("nan"))
)

# La détection d'anomalie se base sur la valeur absolue du modified_z
df["is_anomaly"] = df["modified_z"].abs() > Z_THRESHOLD

fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 8), sharex=True)

ax1.plot(
    df["price_date"], df["price"], label="Prix", color="steelblue", linewidth=1
)
ax1.plot(
    df["price_date"],
    df["rolling_median"],
    label="Médiane mobile (12 mois)",
    color="orange",
    linestyle="--",
)
anomalies = df[df["is_anomaly"]]
ax1.scatter(
    anomalies["price_date"],
    anomalies["price"],
    color="red",
    zorder=5,
    label="Anomalie détectée",
)
ax1.set_ylabel("Prix (XOF)")
ax1.legend()
ax1.set_title("NER-602 / commodity_id=73 / Retail - Prix VS médiane mobile")

ax2.plot(df["price_date"], df["modified_z"], color="purple", linewidth=1)
ax2.axhline(
    Z_THRESHOLD, color="red", linestyle=":", label=f"Seuil ±{Z_THRESHOLD}"
)
ax2.axhline(-Z_THRESHOLD, color="red", linestyle=":")
ax2.set_ylabel("Z-score modifié")
ax2.legend()

plt.tight_layout()
plt.savefig("11_validation_series.png", dpi=120)
print("Graphique sauvegardé : 11_validation_series.png")