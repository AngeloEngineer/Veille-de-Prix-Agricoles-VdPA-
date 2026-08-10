"""
Spike d'exploration : Nous cherchons à valider la source de donnée HDX/WFP Food Prices pour le Togo pour commencer.
Objectif : confirmer l'existence, la structure et la qualité des données
AVANT de concevoir le schema d'ingestion
"""

import requests
import pandas as pd

# Recherche du dataset via l'API CKAN de HDX
SEARCH_URL = "https://data.humdata.org/api/3/action/package_search"
params = {
    "q": "Togo food prices", "rows": 5
}

reponse = requests.get(SEARCH_URL, params= params, timeout=45)
reponse.raise_for_status()
results = reponse.json()["result"]["results"]

print(f"{len(results)} DATASETS(s) TROUVÉ(s) POUR 'Togo food prices' :\n")

csv_url = None
for r in results:
    print(f"- {r['title']} (name: {r['name']})")
    for rep in r.get("ressources", []):
        print(f"  -> {rep['name']} | format={rep['format']} | url={rep['url']}")
        if rep['format'].upper() == "CSV" and csv_url is None:
            csv_url = rep["url"]

if not csv_url:
    print("\n AUCUN FICHIER CSV TROUVÉ AUTOMATIQUEMENT ; INSPECTE LA LISTE CI-DESSUS À LA MAIN.")
else:
    print(f"\n CSV RETENU : {csv_url}")

    # Téléchargement et premier chargement
    df = pd.read_csv(csv_url)

    print("\n ---APERCU STRUCTUREL---")
    print("DIMENSIONS :", df.shape)
    print("\nTYPES :\n", df.dtypes)
    print("\nLES 5 PREMIÈRES LIGNES :\n", df.head())
    print("\nVALEURS MANQUANTES PAR COLONNE :\n", df.isna().sum())