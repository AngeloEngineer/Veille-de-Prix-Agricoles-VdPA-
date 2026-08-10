"""
Découvre des identifiants HDX pour les pays cibles.
Volontairement non-automatisé sur le choix final : On verifie à l'oeil,
en particulier pour distinguer Niger / Nigeria.
"""
import requests
SEARCH_URL = "https://data.humdata.org/api/3/action/package_search"
countries = ["Burkina Faso", "Niger", "Nigeria", "Senegal", "Côte d’Ivoire", "Ghana", "Benin", "Mali"]

for country in countries:
    params ={
        "q": f"{country} food prices", "rows": 5
    }
    reponse = requests.get(SEARCH_URL, params=params, timeout=30)
    reponse.raise_for_status()
    results = reponse.json()["result"]["results"]

    print(f"\n --- Recherche : '{country}' ---")
    for r in results:
        print(f" name = {r['name']:35s} | title = {r['title']}")