"""
`priceflag` feature détectée dans la structure ou schema de données pour tous les pays
(voir l'execution de src/07_profile_multi_country.py), cette feature introduit pour le Nigeria deux valeurs
autrepart jamais vues : aggregate (35 180 lignes, soit plus de 40% du volume Nigeria donc pas un cas marginal) et actual,aggregate

c'est un vrai problème de propreté de données qu'il faudra parser explicitement au staging 
("actual,aggregate" n'est ni "actual" ni "aggregate", c'est une troisième catégorie cachée si on ne la traite pas)

Objectif : puisqu'on n'a pas de définition officielle fiable,on regarde comment ces lignes 
se comportent structurellement pour décider si elles sont fiables ou à exclure de la détection d'anomalies.

Hypothèse à tester : une ligne "aggregate" pourrait être une valeur calculée comme la moyenne ou la médiane 
régionale redistribuée sur plusieurs marchés auquel cas on verrait le même prix apparaître identiquement 
sur plusieurs marchés à la même date pour la même commodité, contrairement à une ligne "actual" qui devrait varier marché par marché.
"""
import pandas as pd
from pymongo import MongoClient

client = MongoClient("mongodb://localhost:27017/")
collection = client["veille_prix_agricoles"]["raw_food_prices"]

docs = list(collection.find({"_country_iso3": "NGA"}, {"_id": 0}))
df = pd.DataFrame(docs)

#1. Comparaison structurelle actual vs aggregate
for flag in ["actual", "aggregate"]:
    subset = df[df["priceflag"] == flag]
    print(f"\n=== priceflag = '{flag}' ({len(subset)} lignes) ===")
    print("Marchés distincts concernés :", subset["market"].nunique())
    print("Commodités distinctes :", subset["commodity"].nunique())

#2. Test de l'hypothèse: un même répété sur plusieurs marchés ?
aggregate_rows = df[df['priceflag'] == "aggregate"]
duplicated_prices = (
    aggregate_rows
    .groupby(["date", "commodity", "price"])["market"]
    .nunique()
    .reset_index(name="nb_marches_avec_ce_prix")
    .sort_values("nb_marches_avec_ce_prix", ascending=False)
)
print("\n--- Un même prix 'aggregate' apparaît-il sur plusieurs marchés le même jour ? ---")
print(duplicated_prices.head(10))

# 3. Exemples concrets de lignes 'actual.aggregate' (valeur combinée suspecte)
combined = df[df["priceflag"] == "actual,aggregate"]
print(f"\n-- Exemples de lignes 'actual,aggregate' ({len(combined)} au total) ---")
print(combined[["date", "market", "commodity", "price", "pricetype"]].head(10))

client.close()