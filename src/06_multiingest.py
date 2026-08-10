"""
Ingestion multi-pays des prix alimentaires WFP vers MongoDB (Zone brute).
Idempotent: chaque exécution remplace intégralement les documents du pays concerné.
Tolérent aux pannes: l'echec d'un pays n'interrompt pas les suivants.
"""
import time
import requests
import pandas as pd
from pymongo import MongoClient
from datetime import datetime, timezone

SHOW_URL = "https://data.humdata.org/api/3/action/package_show"
MONGO_URI = "mongodb://localhost:27017/"
DB_NAME = "veille_prix_agricoles"
COLLECTION_NAME = "raw_food_prices"

#5 premiers pays. CIV/GHA/BEN/MLI restent en réserve dans le dict complet.
MVP_COUNTRIES = {
    "TGO": "wfp-food-prices-for-togo",
    "BFA": "wfp-food-prices-for-burkina-faso",
    "NER": "wfp-food-prices-for-niger",
    "NGA": "wfp-food-prices-for-nigeria",
    "SEN": "wfp-food-prices-for-senegal",
}

def get_prices_csv_url(dataset_id: str) -> str:
    # Resout dynamiquement l'URL du CSV de prix (pas celui des marchés).
    reponse = requests.get(SHOW_URL, {"id": dataset_id}, timeout=30)
    reponse.raise_for_status()
    result = reponse.json()["result"]
    for res in result["resources"]:
        if res["format"].upper() == "CSV" and "market" not in res["name"].lower():
            return res["url"]
    raise ValueError(f"Aucun CSV de prix trouvé pour {dataset_id}")

def ingest_country(dataset_id: str, country_iso3: str, collection) -> tuple[int, int]:
    # Ingère un pays. Retourne le tuple (nb_inseres, nb_supprimes_avant_remplacement)
    csv_url = get_prices_csv_url(dataset_id)
    df = pd.read_csv(csv_url)

    ingested_at = datetime.now(timezone.utc).isoformat()
    records = df.to_dict(orient="records")
    for r in records:
        r["_country_iso3"] = country_iso3
        r["_source_dataset"] = dataset_id
        r["_source_url"] = csv_url
        r["_ingested_at"] = ingested_at

    """Idempotence : on remplace intégralement les documents existants du pays
    Stratégie "full refresh par pays" - simple et correcte tant que le volume reste modeste"""
    deleted = collection.delete_many({"_country_iso3": country_iso3})
    result = collection.insert_many(records)
    return len(result.inserted_ids), deleted.deleted_count

if __name__ == "__main__":
    client = MongoClient(MONGO_URI)
    collection = client[DB_NAME][COLLECTION_NAME]

    summary = {}

    for iso3, dataset_id in MVP_COUNTRIES.items():
        print(f"--- Ingestion {iso3} ---")
        try:
            inserted, deleted = ingest_country(dataset_id, iso3, collection)
            summary[iso3] = f"OK ({inserted} insérés, {deleted} remplacés)"
            print(f" OK: {inserted} documents insérés (remplace {deleted} anciens)")
        except Exception as e:
            summary[iso3] = f"ÉCHEC : {e}"
            print(f" ÉCHEC : {e}")

        time.sleep(1) #Pour eviter d'enchainer les requetes à sec

    print("\n--- Résumé de l'ingestion---")
    for iso3, status in summary.items():
        print(f"{iso3} : {status}")

    print("\nTotal collection pour l'ensemble des pays :", collection.count_documents({}))
    client.close()
        
