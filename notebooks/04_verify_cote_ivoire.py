"""
Il s'agit ici de departager deux deux ids candidats (issue de l'execution de discover_countries.py)
Pour cote d'ivoire via leur fraicheur
"""
import requests

SHOW_URL = "https://data.humdata.org/api/3/action/package_show"
candidates = ["wfp-food-prices-for-cote-d-ivoire","wfp-food-prices-for-cote-divoire"]

for cid in candidates:
    reponse = requests.get(SHOW_URL, params={"id":cid}, timeout=30)
    reponse.raise_for_status()
    result = reponse.json()["result"]
    print(f"\n ---{cid}---")
    print("Titre :", result["title"])
    print("Dernière mise à jour:", result.get("metadata_modified"))
    print("Nombre de resources :", len(result["resources"]))