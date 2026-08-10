"""
Profilage multi-pays de la zone brute MongoDB, avant conception du schéma PostgreSQL.
Objectif : vérifier si les 5 pays partagent bien la même structure de données, 
ou si certains présentent des variations qu'on n'a vues nulle part avec 
le Togo seul (colonnes en plus/en moins, priceflag avec des valeurs estimated, pricetype avec du Wholesale, devises différentes...)
"""
import pandas as pd
from pymongo import MongoClient

MONGO_URI = "mongodb://localhost:27017/"
DB_NAME = "veille_prix_agricoles"
COLLECTION_NAME = "raw_food_prices"

MVP_COUNTRIES = ["TGO", "BFA", "NER", "NGA", "SEN"]

client = MongoClient(MONGO_URI)
collection = client[DB_NAME][COLLECTION_NAME]

for iso3 in MVP_COUNTRIES:
    docs = list(collection.find({"_country_iso3": iso3}, {"_id": 0}))
    df = pd.DataFrame(docs)

    print(f"\n=== {iso3} ({len(df)} lignes) ===")
    print("Colonnes :", sorted(df.columns.tolist()))
    print("Catégories :", df["category"].unique().tolist())
    print("Devises :", df["currency"].unique().tolist())
    print("priceflag :\n", df["priceflag"].value_counts())
    print("pricetype :\n", df["pricetype"].value_counts())
    na = df.isna().sum()
    print("Valeurs manquantes (colonnes concernées) :\n", na[na > 0] if na.any() else "Aucune")

client.close()

