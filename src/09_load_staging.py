"""
Chargement MongoDB (Zone brute) -> PostgreSQL (staging.stg_food_prices).
Copie fidèle et typée, sans logique métier. Idempotent par pays (DELETE + INSERT).
"""
import math
import psycopg2
from psycopg2.extras import execute_values
from pymongo import MongoClient

MONGO_URI = "mongodb://localhost:27017/"
MONGO_DB = "veille_prix_agricoles"
MONGO_COLLECTION = "raw_food_prices"

PG_DSN = "dbname=veille_prix_agricoles"

MVP_COUNTRIES = ["TGO", "BFA", "NER", "NGA", "SEN"]

INSERT_COLUMNS = [
    "country_iso3", "price_date", "admin1", "admin2", "market", "market_id",
    "latitude", "longitude", "category", "commodity", "commodity_id", "unit",
    "priceflag", "pricetype", "currency", "price", "usdprice", "source_dataset",
    "source_url", "ingested_at",
]

def clean(value):
    # Convertit les NaN pandas en None, pour un NULL SQL propre.
    if isinstance(value, float) and math.isnan(value):
        return None
    return value

def mongo_doc_to_row(doc: dict) -> tuple:
    return (
        doc["_country_iso3"], doc["date"], clean(doc.get("admin1")), clean(doc.get("admin2")),
        doc["market"], doc["market_id"], clean(doc.get("latitude")), clean(doc.get("longitude")),
        doc["category"], doc["commodity"], doc["commodity_id"], clean(doc.get("unit")),
        doc["priceflag"], doc["pricetype"], doc["currency"], doc["price"], clean(doc.get("usdprice")),
        doc["_source_dataset"], doc["_source_url"], doc["_ingested_at"],
    )

def load_country(mongo_collection, pg_conn, iso3: str) -> tuple[int, int]:
    docs = list(mongo_collection.find({"_country_iso3": iso3}))
    rows = [mongo_doc_to_row(d) for d in docs]

    with pg_conn.cursor() as cur:
        cur.execute("DELETE FROM staging.stg_food_prices WHERE country_iso3 = %s", (iso3,))
        deleted = cur.rowcount
        execute_values(
            cur,
            f"INSERT INTO staging.stg_food_prices ({', '.join(INSERT_COLUMNS)}) VALUES %s",
            rows,
        )
    pg_conn.commit()
    return len(rows), deleted

if __name__ == "__main__":
    mongo_client = MongoClient(MONGO_URI)
    mongo_collection = mongo_client[MONGO_DB][MONGO_COLLECTION]
    pg_conn = psycopg2.connect(PG_DSN)

    summary = {}
    for iso3 in MVP_COUNTRIES:
        print(f"--- Chargement {iso3} ---")
        try:
            inserted, deleted = load_country(mongo_collection, pg_conn, iso3)
            summary[iso3] = f"OK ({inserted} insérés, {deleted} remplacés)"
            print(f" OK : {inserted} lignes insérées (remplace {deleted} anciennes)")
        except Exception as e:
            pg_conn.rollback() # indispensable : sans ça, la connexion reste "bloquée" après une erreur
            summary[iso3] = f"ÉCHEC : {e}"
            print(f" ÉCHEC  : {e}")

    print("\n--- Résumé du chargement ---")
    for iso3, status in summary.items():
        print(f"{iso3} : {status}")

    with pg_conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM staging.stg_food_prices")
        print("\nTotal staging.stg_food_prices (tous pays) :", cur.fetchone()[0])

    if any(s.startswith("ÉCHEC") for s in summary.values()):
        raise SystemExit(1)

    pg_conn.close()
    mongo_client.close()
