"""Dans la première version le script semblait plant, mais ce qui s'est passé c'est q'il n'a rien trouvé dans les ressources. C'est un résultat silencieux
En creusant plus, la cause probable était que le package_search (l'endpoint utilisé) interroge l'index de recherche de HDX, pas la base de données directement
et cet index n'inclut pas toujours le détail complet des ressources de chaque dataset

Méthode de résolution: dès qu'on connaît le nom exact d'un objet, on arrête d'utiliser l'endpoint de recherche et on bascule sur l'endpoint de lecture directe. J'ai desormais wfp-food-prices-for-togo grâce à m première exécution 
utilisons package_show, qui interroge la base directement et retourne toujours le détail complet."""

"""
Spike d'exploration v2 : ciblage direct via package_show + qualification complète
du dataset avant conception du schéma.
"""
import requests
import pandas as pd

SHOW_URL = "https://data.humdata.org/api/3/action/package_show"
params = {"id": "wfp-food-prices-for-togo"}

resp = requests.get(SHOW_URL, params=params, timeout=30)
resp.raise_for_status()
result = resp.json()["result"]

print("Titre :", result["title"])
print("Dernière mise à jour :", result.get("metadata_modified"))

csv_url = None
markets_url = None
for res in result["resources"]:
    if res["format"].upper() == "CSV" and "market" in res["name"].lower() and markets_url is None:
        markets_url = res["url"]
    elif res["format"].upper() == "CSV" and csv_url is None:
        csv_url = res["url"]

# Chargement des prix 
df = pd.read_csv(csv_url)
df["date"] = pd.to_datetime(df["date"])

print("\n--- Aperçu structurel ---")
print("Dimensions :", df.shape)
print("Colonnes :", list(df.columns))

print("\n--- Qualification ---")
print("Période couverte :", df["date"].min().date(), "->", df["date"].max().date())
print("Marchés uniques :", df["market"].nunique())
print("Catégories :", df["category"].unique())
print("Nombre de commodités uniques :", df["commodity"].nunique())
print("\nRépartition priceflag :\n", df["priceflag"].value_counts())
print("\nRépartition pricetype :\n", df["pricetype"].value_counts())
print("\nValeurs manquantes par colonne :\n", df.isna().sum())

# Coup d'œil sur le référentiel des marchés 
df_markets = pd.read_csv(markets_url)
print("\n--- Référentiel marchés (Togo - Markets) ---")
print("Dimensions :", df_markets.shape)
print(df_markets.head())