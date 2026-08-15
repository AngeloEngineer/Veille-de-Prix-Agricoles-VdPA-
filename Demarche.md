# Veille Prix Agricoles (Agri Price Watch) — Document de passation

**Statut** : projet en cours, phases 1 à 6 **entièrement terminées**. Phase 7 (Airflow) est la prochaine étape. Ce document permet à un agent IA de reprendre le projet sans historique de conversation préalable.

**Porteuse du projet** : Angelique (GitHub : AngeloEngineer). Projet de portfolio data engineering, développé initialement en mentorat pas-à-pas (scripts tapés manuellement, chaque décision vérifiée empiriquement avant d'être actée — voir section 9 pour le style de raisonnement à reproduire).

---

## 1. Objectif du projet

Système d'alerte précoce sur les prix agricoles et la sécurité alimentaire en Afrique de l'Ouest. Le pipeline ingère des données publiques de prix de marché (World Food Programme via HDX) pour plusieurs pays, les structure à travers une architecture ELT (MongoDB → PostgreSQL → dbt), puis applique une détection d'anomalies statistiques pour signaler les hausses de prix inhabituelles. L'objectif final est un dashboard de reporting destiné à des décideurs (ONG, chercheurs, décideurs publics), pas seulement un pipeline technique.

## 2. Architecture technique — vue d'ensemble

```
HDX API (CKAN) 
    → Python (requests + pandas)
    → MongoDB (zone brute "landing zone", 1 doc = 1 ligne de prix + métadonnées de traçabilité)
    → PostgreSQL schéma "staging" (copie typée, zéro logique métier)
    → dbt Core (schéma cible "dbt_dev")
        → models/staging   : lecture fidèle de la source Postgres
        → models/intermediate : application des règles métier (filtrage qualité)
        → models/marts     : modèle en étoile (dimensions + faits) + calcul d'éligibilité
    → dbt marts/fact_food_prices_anomalies : détection d'anomalies (percentile P01/P99)
    → [à construire] dashboard de reporting (Streamlit)
```

**Environnement** : Pop!_OS / Ubuntu 24.04, Python 3.12.3, PostgreSQL 16, MongoDB 8.0.26, Docker installé mais pas encore utilisé pour ce projet (services tournent en natif pour l'instant, conteneurisation prévue en fin de projet — voir section 8, Phase 8).

**Racine du projet** : `~/Mes_Projets/Veille_Prix_Agricoles`. Dépôt GitHub public sous le compte `AngeloEngineer` (nom exact du repo à vérifier via `git remote -v`, ne pas le deviner).

## 3. Conventions non négociables — à respecter sans exception

Ces règles ont été établies après des incidents réels rencontrés pendant le développement. Ne pas les redécouvrir à ses dépens :

1. **Environnement virtuel : toujours `.venv`, avec le point.** Trois noms différents (`.mon_env`, `venv`, puis `.venv`) ont été utilisés par erreur au fil du projet, causant à deux reprises la fuite de l'environnement virtuel entier dans Git (le `.gitignore` ne cible que `.venv/`). Vérifier `ls -la` avant toute manipulation d'environnement.
2. **`git status` avant chaque `git add`, sans exception.** C'est le seul réflexe qui intercepte une fuite de fichier avant le commit plutôt qu'après le push.
3. **`requirements.txt` ne doit jamais contenir à la fois `psycopg2` et `psycopg2-binary`.** Utiliser uniquement `psycopg2-binary` (binaire précompilé, pas de dépendance système). `psycopg2` seul nécessite `libpq-dev` et échoue à la compilation sur cette machine.
4. **Tout fichier `.sql` sous `models/` dans le projet dbt est automatiquement traité comme un modèle**, quel que soit le nom du sous-dossier. Les tests singuliers dbt vont uniquement dans `tests/` à la racine du projet dbt, jamais sous `models/`.
5. **Ne jamais deviner une URL ou un identifiant externe (dataset HDX, définition de flag, etc.).** Toujours vérifier via l'API ou une recherche, puis confirmer empiriquement avec les données réelles avant d'acter une hypothèse. Voir section 9 pour le détail de cette discipline.
6. **`notebooks/*.csv` est dans le `.gitignore`** — les exports de scripts d'exploration ne doivent pas partir sur GitHub.
7. **Avant d'écrire du SQL ou de concevoir un schéma, toujours profiler les données réelles d'abord.** Chaque couche du projet a été précédée d'un script d'exploration/profilage — ne pas sauter cette étape en reprenant le projet.

## 4. Ce qui a été fait — chronologie technique par fichier

### 4.1 — Fondations du repo
Git initialisé, `.venv` créé, `.gitignore` (exclut `.venv/`, `data/`, `notebooks/*.csv`), `README.md` skeleton, dépôt GitHub public créé et connecté. `requirements.txt` présent à la racine, mis à jour au fil du projet (`requests`, `pandas`, `pymongo`, `psycopg2-binary`, `dbt-postgres`, `matplotlib`).

### 4.2 — Découverte des sources de données (dossier `notebooks/`)
Scripts d'exploration ayant interrogé l'API CKAN de HDX (`https://data.humdata.org/api/3/action/`) pour identifier les datasets de prix WFP par pays. Utilisation de `package_search` pour la découverte initiale, puis `package_show` pour la lecture fiable une fois l'identifiant du dataset connu (`package_search` ne retourne pas systématiquement le détail complet des ressources attachées). Un cas d'ambiguïté a été résolu pour la Côte d'Ivoire : deux identifiants existent, seul `wfp-food-prices-for-cote-d-ivoire` (avec tiret) est la source vivante et à jour ; l'autre est une extraction figée depuis 2024.

**Dictionnaire pays → identifiant HDX, validé** :
```
TGO : wfp-food-prices-for-togo        (MVP)
BFA : wfp-food-prices-for-burkina-faso (MVP)
NER : wfp-food-prices-for-niger        (MVP)
NGA : wfp-food-prices-for-nigeria      (MVP)
SEN : wfp-food-prices-for-senegal      (MVP)
GHA : wfp-food-prices-for-ghana        (identifié, pas encore ingéré)
BEN : wfp-food-prices-for-benin        (identifié, pas encore ingéré)
MLI : wfp-food-prices-for-mali         (identifié, pas encore ingéré)
CIV : wfp-food-prices-for-cote-d-ivoire (identifié, pas encore ingéré)
```
Le périmètre "Afrique de l'Ouest" retenu est la classification statistique **UN M49** (16 pays), volontairement préférée à la CEDEAO qui a perdu 3 membres (Mali, Burkina Faso, Niger) en janvier 2025 — un choix de scope politiquement stable plutôt qu'un choix qui date le projet.

### 4.3 — Ingestion vers MongoDB (dossier `src/`)
Script d'ingestion (`ingest_prices.py`, évolué en version multi-pays) : télécharge le CSV de prix depuis HDX (résolution dynamique de l'URL, jamais codée en dur), charge en MongoDB, base `veille_prix_agricoles`, collection `raw_food_prices`. Chaque document reçoit 4 champs de traçabilité : `_country_iso3`, `_source_dataset`, `_source_url`, `_ingested_at`. Pattern d'idempotence retenu : **full refresh par pays** (`delete_many` puis `insert_many` à chaque exécution) — volontairement simple, justifié par le faible volume (~50-90k lignes/pays) et la fréquence mensuelle de la source. Le script boucle sur les 5 pays MVP avec `try/except` individuel par pays (un échec sur un pays n'interrompt pas les autres) et un résumé final.

**État actuel de la zone brute** : 313 332 documents, 5 pays (TGO 47 090, BFA 58 155, NER 68 779, NGA 87 730, SEN 51 578).

### 4.4 — Profilage multi-pays (script dans `src/` ou `notebooks/` selon la version — vérifier avec `find . -name "*profil*"`)
Comparaison structurelle des 5 pays en base brute. Colonnes identiques partout (bonne nouvelle). Trois divergences réelles découvertes, décisives pour la suite :
- **Devises multiples** : XOF pour 4 pays, **NGN pour le Nigeria** — d'où la nécessité de conserver `price` (devise locale) ET `usdprice` côte à côte, jamais l'un sans l'autre.
- **`category` contient `"non-food"`** au Nigeria (en plus d'un éventail de catégories bien plus large que les autres pays, reflet d'une opération WFP de plus grande ampleur).
- **`pricetype`** mélange `Retail` et `Wholesale` dans BFA, NER, NGA (Togo et Sénégal n'ont que du Retail) — dimension à toujours conserver et jamais mélanger dans un même calcul statistique.
- **`priceflag`** au Nigeria contient, en plus de `actual`, deux valeurs supplémentaires : `aggregate` (35 180 lignes) et `actual,aggregate` (1 198 lignes, valeur composite).

### 4.5 — Investigation empirique du flag `aggregate` (`notebooks/`)
Aucune documentation WFP officielle et précise n'a été trouvée pour distinguer `actual` de `aggregate` — la décision a été prise empiriquement. Preuve : des prix identiques au centime près (ex. "Salt" à 250.0) apparaissent sur 15 à 23 marchés différents à la même date pour les lignes `aggregate` — statistiquement impossible pour des observations de terrain indépendantes. Conclusion actée : `aggregate` est une valeur calculée (probablement régionale/nationale) redistribuée sur plusieurs marchés, pas une observation individuelle fiable. `actual,aggregate` montre un pattern différent (tout un lot marché+date partage ce flag combiné, cause non identifiée avec certitude) mais traité avec la même prudence.

**Décision actée** : seul `priceflag = 'actual'` est utilisé pour la détection d'anomalies. Les autres valeurs restent en base (rien n'est supprimé) mais sont exclues des calculs statistiques via une règle dbt explicite, pas un filtre caché.

**Décision actée sur `category = 'non-food'`** : conservée intacte dans le staging comme réserve pour un futur usage "coût de la vie" plus large, mais exclue de la couche intermediate pour le MVP "prix agricoles".

### 4.6 — Schéma PostgreSQL de staging (`sql/001_create_staging_schema.sql`)
Table `staging.stg_food_prices`, copie typée et fidèle du brut Mongo, **zéro logique métier** (principe ELT). Contrainte `UNIQUE (country_iso3, market_id, commodity_id, price_date, pricetype)` — **volontairement sans `priceflag`**, pour que la contrainte échoue bruyamment si `actual` et `aggregate` se disputaient un jour la même combinaison (testé en pratique : aucune violation constatée lors du chargement réel).

### 4.7 — Chargement MongoDB → PostgreSQL (`src/load_staging.py`, numéroté `09_load_staging.py`)
Utilise `psycopg2` (via `psycopg2-binary`) et `execute_values` pour un chargement groupé performant. Idempotent par pays (`DELETE` puis `INSERT`). `rollback()` systématique en cas d'erreur pour ne pas bloquer les pays suivants sur une connexion en état "avorté". **État actuel** : 313 332 lignes chargées dans `staging.stg_food_prices`, correspondance exacte avec MongoDB (zéro perte).

### 4.8 — Projet dbt (`veille_prix_dbt/`)
Initialisé avec dbt Core + adaptateur `dbt-postgres`, cible `dbt_dev` comme schéma de développement. Modèles organisés en 3 couches (`staging` / `intermediate` / `marts`), convention dbt standard.

- **`models/staging/stg_food_prices.sql`** : lecture fidèle de `staging.stg_food_prices` via `{{ source(...) }}`, aucun filtrage. Déclaration de source dans `models/staging/_sources.yml` avec tests `not_null` sur les colonnes clés et `accepted_values` sur `pricetype`.
- **`models/intermediate/int_food_prices_filtered.sql`** : applique les deux règles métier actées (4.5) — `priceflag = 'actual'` ET `category != 'non-food'`. Test singulier associé (`tests/assert_int_food_prices_excludes_non_actual_or_nonfood.sql`) vérifiant qu'aucune ligne exclue ne fuite. **Volumétrie résultante : 275 047 lignes** (TGO/BFA/NER/SEN inchangés, NGA passe de 87 730 à 49 445).
- **`models/marts/dim_commodities.sql`** : référentiel des commodités (`commodity_id`, `commodity`, `category`), testé `unique` — validé empiriquement comme identifiant global cohérent entre pays.
- **`models/marts/dim_markets.sql`** : référentiel des marchés, clé composite `market_key = country_iso3 || '-' || market_id` — choix de conception **défensif** (le `market_id` seul n'est pas garanti unique entre pays, la composite élimine le risque sans avoir à le prouver).
- **`models/marts/fact_food_prices.sql`** : table de faits, référence `market_key` et `commodity_id`. Tests `relationships` (équivalent de clés étrangères) vérifiés en `PASS` — aucun fait orphelin.
- **`models/marts/dim_series_eligibility.sql`** et **`fact_food_prices_eligible.sql`** : voir section 4.9.

### 4.9 — Profilage des séries temporelles et seuil d'éligibilité (`notebooks/`)
Une "série" = un triplet (`market_key`, `commodity_id`, `pricetype`) suivi dans le temps. **4 034 séries distinctes** identifiées, distribution très asymétrique du nombre de points (p25=3, médiane=53, moyenne=68,2, max=436). 440 séries n'ont qu'un seul point : 344 sont de jeunes séries démarrées en 2026 (vont mûrir naturellement), 95 sont des points isolés historiques — dont 82 s'expliquent par 8 dates de "campagnes de collecte" groupées (un pays entier ou un marché entier suivi une seule fois puis abandonné), et seulement 13 sont de vraies observations isolées sans pattern (conservées telles quelles, aucune n'a l'air d'être une erreur de saisie).

**Décision actée** : seuil d'éligibilité = **12 points minimum** (un an d'historique mensuel) pour qu'une série soit utilisée en détection d'anomalies. Matérialisé dans `dim_series_eligibility.sql` (comptage + flag `is_eligible`) et `fact_food_prices_eligible.sql` (jointure filtrée). Test singulier de non-régression associé. **Résultat : 2 616 séries éligibles sur 4 034 (64,8%), soit 211 591 points exploitables.**

### 4.10 — Détection d'anomalies — méthode choisie et validée sur un cas unique (`notebooks/`)
Méthode : médiane mobile + MAD (Median Absolute Deviation), z-score modifié (facteur d'échelle 0,6745, Iglewicz & Hoaglin 1993), fenêtre glissante de 12 mois, seuil initial 3,5. Choisie pour sa robustesse aux valeurs extrêmes (contrairement à moyenne/écart-type classiques). Validée manuellement sur la série la mieux fournie (Niger, marché 602, commodité 73, Retail, 436 points 1990-2026) — le mécanisme identifie correctement les ruptures brutales par rapport à une volatilité récente faible, dans les deux sens (hausse ou baisse), et non une asymétrie liée à la direction du mouvement comme initialement supposé. Une saisonnalité agricole réelle mais modeste a été confirmée (voir 4.11).

### 4.11 — Généralisation aux 2 616 séries éligibles + test de saisonnalité (`notebooks/`)
Généralisation mécanique de la méthode validée en 4.10 à toutes les séries éligibles. **Taux d'anomalies obtenu : 10,05%** (21 263 sur 211 591 points) — considéré comme trop élevé (un seuil à 3,5 écarts-types devrait théoriquement ne flaguer qu'environ 0,05% des points sous une distribution à peu près normale). Test de saisonnalité par mois calendaire effectué : écart entre le mois le plus bas (mars, 8,78%) et le plus haut (novembre, 11,77%) — ratio 1,34x, statistiquement réel mais d'ampleur pratique faible. L'hypothèse d'une "période de soudure" (mai-septembre) élevée de façon continue est **infirmée à l'échelle agrégée** (juin est l'un des mois les plus bas). **Décision actée : pas d'ajustement saisonnier explicite pour le MVP**, l'effet est trop faible pour le justifier.

### 4.12 — Calibrage du seuil/fenêtre — tentative infructueuse (`notebooks/`)
Grille de test sur fenêtre ∈ {12, 18, 24} × seuil ∈ {3,5 ; 5 ; 6}, calculée sur le **prix brut (niveau absolu)**. Les 9 combinaisons restent toutes bien au-dessus d'une cible réaliste de 0,5-2% (meilleur cas : fenêtre 24 / seuil 6 → encore 3,71%). **Diagnostic** : le problème n'est pas un mauvais calibrage, c'est le signal lui-même — mesurer l'écart sur le **niveau de prix absolu** mélange tendance longue, saisonnalité et chocs, qu'aucun couple fenêtre/seuil ne peut démêler proprement.

### 4.13 — Test variation mois/mois (`notebooks/13_2_calibration2.py`)
Changement de signal : détection appliquée sur `(prix_t / prix_t-1) - 1` (variation en %) plutôt que sur le prix brut, même méthode MAD/z-score, fenêtre 12, seuil 3,5. **Résultat : 7,98%** (16 574 anomalies sur 207 604 points) — amélioration réelle par rapport aux 10,05% du prix brut, mais **toujours loin de la cible de 0,5-2%**. Ce résultat a motivé l'abandon définitif de l'approche MAD/z-score au profit des percentiles (voir 4.14–4.16).

### 4.14 — Profilage pré-implémentation percentile (`notebooks/14_profil_avant_percentile.py`)
Avant d'écrire le modèle dbt, profilage complet de la distribution des variations mois/mois. Résultats clés :
- **0 infini** (aucun `price_t-1 = 0`) et **0 variation à -100%** (aucun prix tombant à 0) — données propres sur ce point.
- **67 groupes** (commodity_id + pricetype), taille médiane 1 237 points par groupe (p25=678, max=44 792) — très confortable pour des percentiles stables.
- **4 groupes < 50 points** (dont 3 < 30) : seuil `min_n_group = 30` acté pour exclure les percentiles non fiables.
- Simulation préalable : taux attendu **1,99%** avec P01/P99 — conforme à la cible avant même d'écrire le SQL.

### 4.15 — Investigation des groupes suspects (`notebooks/15_investigate_suspects.py`)
8 groupes présentaient des seuils extrêmes (P01 < -80% ou P99 > +300%). Investigation empirique cas par cas :
- **Lait en poudre Nigeria (cid 238)** : hausse +3025% en mai 2022 → choc NGN réel (crise monétaire Nigeria 2022), pas un artéfact. Flagué à juste titre.
- **Cowpeas brown Wholesale Nigeria (cid 480)** : hausse +9211% en janvier 2019 (`NGA-1971` : 216 NGN → 19 400 NGN) → artéfact probable (changement d'unité NGN). Mais le P99 du groupe (3,15) n'est pas faussé par cet outlier extrême ; la valeur à 92x est elle-même flaggée comme anomalie — comportement correct.
- **Épinards, bananes, oranges, poisson Nigeria** : saisonnalité forte (produits frais), pattern de chutes/hausses brutales entre saisons — signal économique réel, pas des artéfacts.
- **Décision actée** : pas de clip/trim des variations extrêmes. Les chocs réels et les artéfacts doivent tous être flagués, pas masqués dans les seuils.

### 4.16 — Validation finale anti-écatombe + matérialisation dbt (`notebooks/16_validation_finale_percentile.py`)
Validation exhaustive avant implémentation : contrôle que le taux global de 1,99% ne cache pas une distribution pathologique sur un sous-ensemble.

**Résultats des contrôles anti-écatombe** :

| Dimension | Taux max observé | Seuil d'alerte | Résultat |
|---|---|---|---|
| Pays | NGA 2,96% / TGO 2,86% | > 10% | ✅ |
| Catégorie de commodité | Huiles 2,09% | > 10% | ✅ |
| Commodité individuelle | Wheat Wholesale 4,17% (n=48) | > 15% | ✅ |
| Temporel | 1996 : 5,67% / 2005 : 6,64% | > 5% = choc réel | ✅ cohérent |

Les années à taux élevé (1996, 2005, 2022) correspondent à des crises économiques documentées — pas à un bug.

**Modèle dbt livré** : `models/marts/fact_food_prices_anomalies.sql` (matérialisé en `table`). Colonnes ajoutées par rapport à `fact_food_prices_eligible` : `pct_change`, `threshold_p01`, `threshold_p99`, `n_group_for_threshold`, `is_anomaly` (BOOLEAN, jamais NULL), `anomaly_direction` ('hausse'/'baisse'/'normal'/'non_evalue'), `anomaly_severity` (distance au seuil dépassé).

**Test singulier de garde-fou** : `tests/assert_anomaly_rate_in_bounds.sql` — échoue si le taux global sort des bornes [0,5% ; 5,0%] ou si la table contient moins de 100 000 points (protection contre un bug silencieux qui viderait la table).

**`dbt build` complet : 49/49 PASS, WARN=0, ERROR=0.** Commit `fb062e4`.

### 4.17 — Installation Airflow (Phase 7, démarrage)
Airflow 3.3.1 installé dans le même `.venv` que dbt (Python 3.12.3), via le fichier de contraintes officiel résolu dynamiquement contre PyPI. `pip` a signalé un conflit de versions transitives (`pathspec`, `more-itertools`) entre les dépendances d'Airflow et celles de `dbt-common`/`metricflow`. Vérifié empiriquement avant d'agir (jamais de correction sans diagnostic, convention #6) : `dbt build` complet rejoué, 49/49 PASS identique à la référence Phase 6 (commit `fb062e4`), volumétrie `fact_food_prices_anomalies` inchangée (270 861 lignes). **Décision actée** : conflit traité comme faux positif — `dbt-common`/`metricflow` portent le Semantic Layer dbt, non utilisé dans ce projet, donc leurs bornes de version n'affectent pas les commandes réellement exécutées. Un seul `.venv` conservé pour tout le projet, pas de scission dbt/Airflow. À re-vérifier si dbt ou Airflow est mis à jour ultérieurement.

### 4.18 — Emplacement des DAGs (Phase 7)
Par défaut Airflow cherche les DAGs dans `$AIRFLOW_HOME/dags`, or `airflow_home/` est entièrement exclu du versioning (état runtime local). Décision : dossier `dags/` créé à la racine du repo (versionné), Airflow pointé dessus via `export AIRFLOW__CORE__DAGS_FOLDER="$(pwd)/dags"`. Mécanisme validé avec un DAG minimal (`test_setup_veille_prix`), déclenché manuellement, succès. **Point de vigilance non résolu** : cet export (ainsi que `AIRFLOW_HOME`) n'est pas persistant — à refaire à chaque nouvelle session shell tant qu'aucun script de démarrage n'est mis en place. À adresser si la friction devient réelle, pas avant comme ca, on évite la sur-ingénierie prématurée.

### 4.19 — Pipeline complet Airflow (Phase 7)
DAG `veille_prix_pipeline` (`dags/veille_prix_pipeline.py`), 3 tâches séquentielles : `ingestion_multi_pays` (`06_multiingest.py`) >> `chargement_staging` (`09_load_staging.py`) >> `dbt_build` (`dbt build`). Chaque script Python porte un garde-fou explicite (`raise SystemExit(1)` si un pays échoue) pour qu'Airflow détecte un échec partiel silencieux ; `dbt build` s'appuie nativement sur son propre code de sortie, pas de garde-fou custom nécessaire. Validation empirique bout-en-bout : run manuel complet, 3/3 tâches vertes, 318 016 lignes ingérées et chargées en staging, `dbt build` exit 0. Schedule défini à `@monthly`, `catchup=False`.
**Point de vigilance non résolu** (cf. 4.18) : `AIRFLOW_HOME`/`AIRFLOW__CORE__DAGS_FOLDER` doivent être exportés à chaque session, et rien ne garantit que le scheduler tourne en continu pour honorer `@monthly` automatiquement — à traiter en phase suivante.

## 5. Décisions de conception actées — résumé consolidé

| # | Décision | Statut |
|---|---|---|
| 1 | Conserver `price` (devise locale) ET `usdprice` en permanence, jamais l'un sans l'autre | Actée, implémentée |
| 2 | `pricetype` (Retail/Wholesale) toujours une dimension explicite, jamais mélangée dans un calcul | Actée, implémentée |
| 3 | Seul `priceflag='actual'` fiable pour les statistiques ; `aggregate` conservé en base mais exclu en aval | Actée, implémentée (couche intermediate) |
| 4 | `category='non-food'` conservée en réserve (staging), exclue du MVP en aval | Actée, implémentée |
| 5 | Périmètre géographique = UN M49 Afrique de l'Ouest (16 pays), pas CEDEAO | Actée |
| 6 | MVP = 5 pays (TGO, BFA, NER, NGA, SEN), 4 pays supplémentaires identifiés mais non ingérés (GHA, BEN, MLI, CIV) | Actée |
| 7 | `market_key` composite (pays+market_id) — conception défensive, coût nul | Actée, implémentée |
| 8 | Seuil d'éligibilité statistique = 12 points minimum par série | Actée, implémentée |
| 9 | Méthode d'anomalie = percentile P01/P99 par groupe (commodity_id + pricetype) sur variation mois/mois | Actée, implémentée (remplace MAD/z-score abandonné) |
| 10 | Pas d'ajustement saisonnier explicite pour le MVP | Actée |
| 11 | Signal = variation mois/mois sur `price` (devise locale), pas `usdprice` | Actée, implémentée — évite les faux positifs liés à la dévaluation NGN |
| 12 | Groupes avec < 30 points de variation évaluable exclus du flaggage (seuil percentile non fiable) | Actée, implémentée (`min_n_group = 30` dans le SQL) |
| 13 | Pas de clip/trim des variations extrêmes avant calcul des percentiles | Actée — les chocs réels et artéfacts doivent être flagués, pas masqués |

## 6. État des données à date

- Zone brute MongoDB (`veille_prix_agricoles.raw_food_prices`) : 313 332 documents, 5 pays.
- Staging PostgreSQL (`staging.stg_food_prices`) : 313 332 lignes, correspondance exacte avec Mongo.
- dbt intermediate (`dbt_dev.int_food_prices_filtered`) : 275 047 lignes (post-filtrage qualité).
- dbt marts — faits éligibles (`dbt_dev.fact_food_prices_eligible`) : 270 861 lignes, 2 616 séries éligibles (sur 4 034 séries totales).
- dbt marts — anomalies (`dbt_dev.fact_food_prices_anomalies`) : **270 861 lignes**, **5 331 anomalies détectées (1,99%)** — 2 675 hausses (1,00%) + 2 656 baisses (0,99%). Table matérialisée, `dbt build` 49/49 PASS.

**Répartition des anomalies par pays** : BFA 1,07% — NER 1,72% — NGA 2,96% — SEN 1,70% — TGO 2,86%. Aucun pays ni aucune catégorie au-dessus de 10% (contrôle anti-écatombe validé).

## 7. ~~Problème non résolu~~ → Résolu en Phase 6

Le calibrage MAD + z-score avait échoué à atteindre la cible (meilleur résultat : 7,98% avec signal variation mois/mois). **L'approche par percentile non-paramétrique a résolu le problème** (voir sections 4.14–4.16) :

- Signal : variation mois/mois sur `price` (devise locale)
- Seuils : P01 et P99 calculés par groupe (`commodity_id + pricetype`)
- Résultat obtenu : **1,99%** — dans la cible [0,5% ; 2%], symétrique (hausse 1,00% / baisse 0,99%)
- Matérialisé en `dbt_dev.fact_food_prices_anomalies`, testé et validé

**Formulation pour le reporting (Phase 10)** : "ce mouvement de prix fait partie des 2% les plus extrêmes jamais observés pour cette denrée" — message naturel pour un décideur non technique, bien plus parlant qu'un z-score abstrait.

## 8. Feuille de route restante — directives par phase

### ~~Phase 6~~ ✅ CLÔTURÉE — Détection d'anomalies
Implémentée via percentile P01/P99 par groupe commodité+type. Modèle `models/marts/fact_food_prices_anomalies.sql` matérialisé en table. Test de garde-fou `tests/assert_anomaly_rate_in_bounds.sql` [0,5% ; 5,0%]. `dbt build` 49/49 PASS. Commit `fb062e4`. Voir sections 4.14–4.16 pour le détail complet.

### Phase 7 (prochaine étape) — Orchestration Airflow
Un seul DAG, séquence : ingestion multi-pays → chargement staging → `dbt build` (toutes couches) → (optionnel) régénération d'un export de reporting. Fréquence : mensuelle (alignée sur la cadence de mise à jour de la source HDX, confirmée en Mission 2 comme récente à quelques jours près). Ne pas complexifier avec plusieurs DAGs pour un MVP — un seul pipeline linéaire suffit et se défend mieux en entretien qu'une orchestration sur-conçue.

### Phase 8 — Docker Compose
Conteneuriser pour la reproductibilité (Postgres, MongoDB, Airflow, éventuellement Metabase). Contrainte forte : budget disque partagé avec d'autres projets (~25 Go au total) — utiliser des images officielles allégées (`-slim`/`-alpine` quand disponible), ne pas dupliquer les services déjà natifs pendant le développement (le natif reste la référence de dev, Docker Compose est le livrable de reproductibilité finale, pas l'environnement de travail quotidien).

### Phase 9 — CI/CD GitHub Actions
Un seul workflow : lint Python (ruff ou flake8) + `dbt compile`/`dbt test` contre un service PostgreSQL éphémère en CI. Ne pas viser un pipeline multi-étapes élaboré — l'objectif est de démontrer la compétence CI/CD, pas de construire une usine à gaz pour un projet solo.

### Phase 10 — Reporting et storytelling (priorité forte, c'est la partie la plus visible du projet)
Recommandation d'outil : **Streamlit** (contrôle total sur la narration et le code Python déjà maîtrisé sur ce projet) plutôt que Metabase (plus générique, moins de contrôle narratif) — sauf si l'agent identifie une contrainte qui justifie l'inverse.

**Directives de contenu, pour réduire la charge cognitive du décideur** :
- La vue par défaut doit répondre à 3 questions, dans cet ordre : (1) *Où est-ce anormal maintenant ?* — liste courte des anomalies les plus récentes/sévères, pas les 2 616 séries d'un coup ; (2) *Est-ce ponctuel ou une tendance installée ?* — contexte visuel (graphique prix + médiane mobile) pour chaque anomalie affichée ; (3) *Quoi faire concrètement ?* — une liste actionnable (marché, commodité, pays), pas seulement un graphique agrégé.
- Utiliser un code couleur simple (type feu tricolore) pour la sévérité plutôt que des valeurs statistiques brutes affichées en premier plan.
- Un seul message clé par visuel — éviter les tableaux de bord denses en première vue, permettre le "drill-down" vers le détail plutôt que tout montrer d'emblée.
- S'appuyer sur le vocabulaire de percentile recommandé en section 7 pour formuler les messages ("parmi les 2% de mouvements les plus extrêmes"), plus parlant qu'un z-score pour un public non technique.

### Phase 11 — Documentation et préparation entretien
README public reconstruit à partir de ce document (version condensée, orientée lecteur externe plutôt qu'agent IA). Documenter explicitement le parcours d'investigation qualité (sections 4.5, 4.9, 4.12, 4.13 de ce document) — **c'est une valeur ajoutée du projet en soi**, à ne pas résumer en une ligne : la rigueur de découverte de `aggregate`, du seuil d'éligibilité, et l'échec puis la correction du calibrage sont exactement le genre de récit qui démontre une compétence Data Analytics en entretien, davantage qu'un dashboard fini sans le raisonnement derrière.

**Tâche annexe, priorité basse** : étendre l'ingestion aux 4 pays déjà identifiés (GHA, BEN, MLI, CIV) — extension triviale du dictionnaire de configuration existant, aucun nouveau code requis. À faire seulement une fois les phases 6-10 stabilisées, jamais avant.

## 9. Principes de raisonnement à reproduire

Ce projet a été construit avec une discipline précise, à maintenir pour rester cohérent avec ce qui précède :

1. **Ne jamais deviner une donnée externe (URL, définition, structure) — toujours vérifier**, par recherche puis par preuve empirique sur les données réelles. Une hypothèse non vérifiée reste une hypothèse, jamais actée comme un fait.
2. **Profiler avant de concevoir.** Chaque schéma, chaque seuil, chaque règle de filtrage de ce projet a été précédé d'un script d'exploration sur les données réelles — jamais déduit uniquement de la documentation ou de l'intuition.
3. **MVP avant généralisation.** Valider un mécanisme sur un cas unique (un pays, une série) avant de l'appliquer à l'échelle. Garder une configuration extensible en réserve (le dictionnaire à 9 pays) sans la déployer avant que le socle soit prouvé.
4. **Documenter la décision et sa raison, pas seulement le résultat.** Chaque choix de ce document (section 5) porte sa justification — un agent qui reprend le projet doit pouvoir comprendre *pourquoi*, pas seulement appliquer *quoi*.
5. **Séparer le brut, le typé, et le métier.** La discipline staging/intermediate/marts n'est pas une convention arbitraire — elle garantit qu'une donnée brute reste toujours récupérable même si une règle métier s'avère erronée plus tard.
6. **Livrer de la valeur sans s'éparpiller dans la calibration infinie.** Leçon tirée en Phase 6 : quand une itération de calibrage n'a pas convergé après 2-3 tentatives raisonnables, changer d'approche plutôt que de multiplier les variantes du même réglage (la solution percentile a rompu délibérément avec la boucle MAD/z-score plutôt que de la poursuivre — et a atteint la cible dès la première implémentation).
7. **Chaque commit correspond à une unité de travail complète et testée**, pas à un état intermédiaire cassé — vérifier `git status` puis `dbt build`/tests avant de committer.

---

*Fin du document de passation. Toute reprise du projet doit commencer par `find . -name "*.py" -o -name "*.sql"` (hors dossiers ignorés) pour confirmer l'inventaire exact des fichiers avant de s'appuyer sur les chemins mentionnés ci-dessus.*