"""
Objectif: prouver que la méthode statistique choisie fonctionne concrètement sur un cas
réel avant de l'appliquer sur les 2616 séries éligibles. On prendra le cas du Togo
Pour valider à petite échelle afin de faire la validation à grande échelle

La méthode que je veux utiliser: c'est la médiane mobile + le Median Absolute Deviation (MAD) + Z-score modifié

-La médiane mobile et le Median absolute Deviation résistent bien mieux au piège
des valeurs extrèmes; Quelques valeurs extrèmes ne suffisent pas à déplacer une médiane.

- C'est la méthode recommandée par Iglewicz & Hoaglin pour ce type de détection avec u
seuille de 3.5 sur le Z-score modifié
"""
import numpy as np
import pandas as pd
import psycopg2

PG_DSN = "dbname=veille_prix_agricoles"
FENETRE = 12 # Nombre de mois de recul pour la médiane mobile, valeur cohérente avec le seul d'éligibilité
Z_THRESHOLD = 3.5 # Seuil standard

conn = psycopg2.connect(PG_DSN)

#1. Choisir dynamiquement la série la plus fournie
top_series = pd.read_sql(
    """
SELECT market_key, commodity_id, pricetype, nb_points
FROM dbt_dev.dim_series_eligibility
ORDER BY nb_points DESC
LIMIT 1
""",
conn)
market_key, commodity_id, pricetype, nb_points = top_series.iloc[0]
print(f"Série choisie: {market_key} / commodity_id={commodity_id} / {pricetype} ({nb_points} points)")

#2. Charger la série, triée chronologiquement
df = pd.read_sql(
    """
SELECT price_date, price
FROM dbt_dev.fact_food_prices_eligible
WHERE market_key = %(market_key)s AND commodity_id = %(commodity_id)s AND pricetype = %(pricetype)s
ORDER BY price_date
  """,
con=conn,
params= {"market_key": market_key, "commodity_id": int(commodity_id), "pricetype": pricetype}
)
conn.close()

#3. Médiane mobile + MAD sur fenêtre glissante de 12 mois
df["rolling_median"] = df["price"].rolling(window=FENETRE, min_periods=FENETRE).median()
df["rolling_mad"] = df["price"].rolling(window=FENETRE, min_periods=FENETRE).apply(lambda x: np.median(np.abs(x - np.median(x))), raw=True)

#4. Z-score modifié: 0.6745 est un facteur d'échelle qui rend le MAD comparable à un écart-type sous une hypothèse de normalité
df["modified_z"] = 0.6745*(df["price"] - df["rolling_median"])/df["rolling_mad"].replace(0, np.nan)
df["is_anomaly"] = df["modified_z"].abs()>Z_THRESHOLD

#5. Réaultats
nb_evaluable = df["modified_z"].notna().sum()
nb_anomalies = df["is_anomaly"].sum()
print(f"\nPoints évaluables sur la fenètre de {FENETRE} mois pleine : {nb_evaluable} / {len(df)}")
print(f"Anomalies détectées (|Z| > {Z_THRESHOLD}) : {nb_anomalies}")

print("\n --- Table complète ---")
pd.set_option("display.max_rows", None)
print(df.to_string(index=False))