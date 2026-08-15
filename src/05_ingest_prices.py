"""
Ingestion des prix alimentaires WFP vers MongoDB (zone brute / landing zone).
Un document Mongo par ligne de prix, avec métadonnées de tracabilité.
"""
import requests
import pandas as pd
from pymongo import MongoClient
from datetime import datetime, timezone

SHOW_URL = "https://data.humdata.org/api/3/action/package_show"

MONGO_URI = "mongodb://localhost:27017/"
DB_NAME = "veille_prix_agricoles"
COLLECTION_NAME = "raw_food_prices"

def get_prices_csv_url(dataset_id: str) -> str:
    #Résout dynamiquement l'url du CSV de prix
    reponse = requests.get(SHOW_URL, params={"id": dataset_id}, timeout=30)
    reponse.raise_for_status()
    result = reponse.json()["result"]
    for res in result["resources"]:
        if res["format"].upper() == "CSV" and "market" not in res["name"].lower(): #Non ne veut pas resoudre les url des marchés, que ceux des prix
            return res["url"]
    raise ValueError(f"Aucun CSV de prix trouvé pour {dataset_id}")

def ingest_country(dataset_id: str, country_iso3: str, collection) -> int:
    csv_url = get_prices_csv_url(dataset_id)
    df = pd.read_csv(csv_url)

    ingested_at = datetime.now(timezone.utc).isoformat()
    records = df.to_dict(orient="records")
    for r in records:
        r["_country_iso3"] = country_iso3
        r["_source_dataset"] = dataset_id
        r["_source_url"] = csv_url
        r["_ingested_at"] = ingested_at

    result = collection.insert_many(records)
    return len(result.inserted_ids)

if __name__ == "__main__":
    client = MongoClient(MONGO_URI)
    collection = client["DB_NAME"][COLLECTION_NAME]

    inserted = ingest_country("wfp-food-prices-for-togo", "TGO", collection)

    print(f"{inserted} documents insérés pour TGO.")
    print("Documents TGO en base :", collection.count_documents({"_country_iso3": "TGO"}))
    print("\nTotal collection tous pays :", collection.count_documents({}))

    