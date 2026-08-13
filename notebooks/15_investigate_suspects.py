"""
Phase 6 — Investigation des groupes suspects avant de les inclure ou exclure.

CONTEXTE : Le profilage (script 14) a identifié :
  - 3 groupes avec P01 < -80%  (commodity_id : 62 Wholesale, 238 Retail, 404 Retail)
  - 8 groupes avec P99 > +300% (commodity_id : 139, 238, 254, 360, 404, 479, 480 Retail, 480 Wholesale)

Pour chaque groupe suspect, on inspecte :
  1. Quelle commodité est-ce ? (via dbt_dev.dim_commodities)
  2. Comment est distribuée la variation pct_change ?
  3. Y a-t-il des valeurs extrêmes qui tirent les percentiles ?
  4. Ces extrêmes sont-ils des chocs économiques réels ou des artéfacts de saisie ?

DÉCISION VISÉE : soit inclure tel quel (les extrêmes sont réels), soit corriger le
calcul (clip de pct_change avant calcul du percentile), soit exclure les groupes
trop petits ou trop bruités.
"""

import psycopg2
import pandas as pd
import numpy as np

PG_DSN = "dbname=veille_prix_agricoles"
conn = psycopg2.connect(PG_DSN)

# 1. Récupérer les noms des commodités suspectes
print("=" * 60)
print("INVESTIGATION DES GROUPES SUSPECTS")
print("=" * 60)

suspects = [62, 238, 404, 139, 254, 360, 479, 480]
commo_names = pd.read_sql("""
    SELECT commodity_id, commodity, category
    FROM dbt_dev.dim_commodities
    WHERE commodity_id = ANY(%(ids)s)
""", conn, params={"ids": suspects})
print("\nNoms des commodités suspectes :")
print(commo_names.to_string(index=False))

# 2. Charger toutes les variations pour les groupes suspects
print("\n" + "-" * 60)
print("DÉTAIL PAR GROUPE SUSPECT")
print("-" * 60)

df = pd.read_sql("""
    SELECT market_key, commodity_id, pricetype, price_date, price
    FROM dbt_dev.fact_food_prices_eligible
    WHERE commodity_id = ANY(%(ids)s)
    ORDER BY commodity_id, pricetype, market_key, price_date
""", conn, params={"ids": suspects})
conn.close()

df["price_date"] = pd.to_datetime(df["price_date"])
df["pct_change"] = df.groupby(["market_key","commodity_id","pricetype"])["price"].pct_change()
df_eval = df[df["pct_change"].notna() & ~np.isinf(df["pct_change"])].copy()

for cid in suspects:
    for ptype in ["Retail", "Wholesale"]:
        sub = df_eval[(df_eval["commodity_id"] == cid) & (df_eval["pricetype"] == ptype)]
        if len(sub) == 0:
            continue
        
        name_row = commo_names[commo_names["commodity_id"] == cid]
        name = name_row["commodity"].values[0] if len(name_row) > 0 else "?"
        
        p01 = np.percentile(sub["pct_change"], 1)
        p99 = np.percentile(sub["pct_change"], 99)
        print(f"\n{'='*50}")
        print(f"  commodity_id={cid} ({name}) — {ptype}")
        print(f"  N = {len(sub):,} points, {sub['market_key'].nunique()} marchés")
        print(f"  P01={p01:.4f}  P10={np.percentile(sub['pct_change'],10):.4f}  "
              f"P25={np.percentile(sub['pct_change'],25):.4f}  "
              f"P50={np.percentile(sub['pct_change'],50):.4f}  "
              f"P75={np.percentile(sub['pct_change'],75):.4f}  "
              f"P90={np.percentile(sub['pct_change'],90):.4f}  P99={p99:.4f}")
        print(f"  Min={sub['pct_change'].min():.4f}  Max={sub['pct_change'].max():.4f}")
        
        # Les 5 valeurs les plus extrêmes en baisse
        extreme_bas = sub.nsmallest(5, "pct_change")[["market_key","price_date","price","pct_change"]]
        print(f"\n  5 plus grandes baisses :")
        print(extreme_bas.to_string(index=False))
        
        # Les 5 valeurs les plus extrêmes en hausse
        extreme_haut = sub.nlargest(5, "pct_change")[["market_key","price_date","price","pct_change"]]
        print(f"\n  5 plus grandes hausses :")
        print(extreme_haut.to_string(index=False))

print("\n" + "=" * 60)
print("FIN INVESTIGATION")
print("=" * 60)
