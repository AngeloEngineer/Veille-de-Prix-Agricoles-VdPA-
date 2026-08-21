# Veille Prix Agricoles — Agri Price Watch — Document de passation

**Statut** : projet en cours, phases 1 à 6 **entièrement terminées**. La Phase 7 d'orchestration Airflow constitue la prochaine étape. Ce document permet à un agent IA de reprendre le projet sans historique de conversation préalable.

**Porteuse du projet** : Angelique, sur le compte GitHub AngeloEngineer. Projet de portfolio data engineering, développé initialement en mentorat pas-à-pas, avec des scripts tapés manuellement et chaque décision vérifiée empiriquement avant d'être actée. Se référer à la section 9 pour le style de raisonnement à reproduire.

---

## 1. Objectif du projet

Système d'alerte précoce sur les prix agricoles et la sécurité alimentaire en Afrique de l'Ouest. Le pipeline ingère des données publiques de prix de marché provenant du World Food Programme via la plateforme HDX pour plusieurs pays. Il les structure à travers une architecture ELT articulée autour de MongoDB, PostgreSQL et dbt, puis applique une détection d'anomalies statistiques pour signaler les hausses de prix inhabituelles. L'objectif final est un dashboard de reporting destiné à des décideurs tels que les ONG, les chercheurs et les décideurs publics, et non à constituer seulement un pipeline technique.

## 2. Architecture technique — vue d'ensemble

```
HDX API — CKAN
    → Python via requests et pandas
    → MongoDB : zone brute de type landing zone, où un document correspond à une ligne de prix avec ses métadonnées de traçabilité
    → PostgreSQL schéma staging : copie typée sans aucune logique métier
    → dbt Core vers le schéma cible dbt_dev
        → models/staging   : lecture fidèle de la source Postgres
        → models/intermediate : application des règles métier et filtrage qualité
        → models/marts     : modèle en étoile avec dimensions et faits, puis calcul d'éligibilité
    → dbt marts/fact_food_prices_anomalies : détection d'anomalies selon les percentiles P01 et P99
    → Dashboard de reporting Streamlit
```

**Environnement** : Pop!_OS / Ubuntu 24.04, Python 3.12.3, PostgreSQL 16, MongoDB 8.0.26, Docker installé mais pas encore utilisé pour ce projet. Les services tournent en natif pour l'instant et la conteneurisation complète est traitée en Phase 8 selon la section 8.

**Racine du projet** : `~/Mes_Projets/Veille_Prix_Agricoles`. Dépôt GitHub public sous le compte `AngeloEngineer`. Le nom exact du dépôt est à vérifier au préalable via la commande `git remote -v` sans le deviner.

## 3. Conventions non négociables — à respecter sans exception

Ces règles ont été établies après des incidents réels rencontrés pendant le développement. Ne pas les redécouvrir à ses dépens :

1. **Environnement virtuel : toujours `.venv`, avec le point.** Trois noms différents comme `.mon_env`, `venv` puis `.venv` ont été utilisés par erreur au fil du projet, causant à deux reprises la fuite de l'environnement virtuel entier dans Git car le fichier `.gitignore` cible exclusivement `.venv/`. Vérifier via `ls -la` avant toute manipulation d'environnement.
2. **`git status` avant chaque `git add`, sans exception.** C'est le seul réflexe qui intercepte une fuite de fichier avant le commit plutôt qu'après le push.
3. **`requirements.txt` ne doit jamais contenir à la fois `psycopg2` et `psycopg2-binary`.** Utiliser uniquement `psycopg2-binary`, qui est un binaire précompilé sans dépendance système. La bibliothèque `psycopg2` seule nécessite `libpq-dev` et échoue à la compilation sur cette machine.
4. **Tout fichier `.sql` sous `models/` dans le projet dbt est automatiquement traité comme un modèle**, quel que soit le nom du sous-dossier. Les tests singuliers dbt vont uniquement dans `tests/` à la racine du projet dbt, jamais sous `models/`.
5. **Ne jamais deviner une URL ou un identifiant externe tel qu'un dataset HDX ou une définition de flag.** Toujours vérifier via l'API ou une recherche, puis confirmer empiriquement avec les données réelles avant d'acter une hypothèse. Se référer à la section 9 pour le détail de cette discipline.
6. **`notebooks/*.csv` est dans le `.gitignore`** — les exports de scripts d'exploration ne doivent pas partir sur GitHub.
7. **Avant d'écrire du SQL ou de concevoir un schéma, toujours profiler les données réelles d'abord.** Chaque couche du projet a été précédée d'un script d'exploration et de profilage — ne pas sauter cette étape en reprenant le projet.

## 4. Ce qui a été fait — chronologie technique par phase

### Phase 1 — Fondations du dépôt et environnement

#### 4.1 — Fondations du repo
Git initialisé, `.venv` créé, `.gitignore` configuré pour exclure `.venv/`, `data/` ainsi que `notebooks/*.csv`, squelette `README.md` rédigé, dépôt GitHub public créé et connecté. Le fichier `requirements.txt` est présent à la racine et mis à jour au fil du projet avec notamment `requests`, `pandas`, `pymongo`, `psycopg2-binary`, `dbt-postgres` et `matplotlib`.

### Phase 2 — Découverte des sources de données

#### 4.2 — Découverte des sources de données dans le dossier notebooks
Scripts d'exploration ayant interrogé l'API CKAN de HDX via l'URL `https://data.humdata.org/api/3/action/` pour identifier les datasets de prix WFP par pays. Utilisation de `package_search` pour la découverte initiale, puis de `package_show` pour la lecture fiable une fois l'identifiant du dataset connu, car `package_search` ne retourne pas systématiquement le détail complet des ressources attachées. Un cas d'ambiguïté a été résolu pour la Côte d'Ivoire : deux identifiants existent et seul `wfp-food-prices-for-cote-d-ivoire` avec tiret est la source vivante et à jour ; l'autre est une extraction figée depuis 2024.

**Dictionnaire pays vers identifiant HDX validé** :
```
TGO : wfp-food-prices-for-togo        — MVP
BFA : wfp-food-prices-for-burkina-faso — MVP
NER : wfp-food-prices-for-niger        — MVP
NGA : wfp-food-prices-for-nigeria      — MVP
SEN : wfp-food-prices-for-senegal      — MVP
GHA : wfp-food-prices-for-ghana        — identifié, non ingéré
BEN : wfp-food-prices-for-benin        — identifié, non ingéré
MLI : wfp-food-prices-for-mali         — identifié, non ingéré
CIV : wfp-food-prices-for-cote-d-ivoire — identifié, non ingéré
```
Le périmètre Afrique de l'Ouest retenu est la classification statistique **UN M49** regroupant 16 pays, volontairement préférée à la CEDEAO qui a perdu 3 membres soit le Mali, le Burkina Faso et le Niger en janvier 2025. C'est un choix de scope politiquement stable plutôt qu'un choix qui date le projet.

### Phase 3 — Ingestion et zone brute MongoDB

#### 4.3 — Ingestion vers MongoDB dans le dossier src
Script d'ingestion `ingest_prices.py`, évolué en version multi-pays : télécharge le CSV de prix depuis HDX grâce à une résolution dynamique de l'URL sans jamais la coder en dur, puis charge en MongoDB dans la base `veille_prix_agricoles` et la collection `raw_food_prices`. Chaque document reçoit 4 champs de traçabilité : `_country_iso3`, `_source_dataset`, `_source_url` et `_ingested_at`. Pattern d'idempotence retenu : **full refresh par pays** via un `delete_many` suivi d'un `insert_many` à chaque exécution. Cela reste volontairement simple et se justifie par le faible volume d'environ 50k à 90k lignes par pays et par la fréquence mensuelle de la source. Le script boucle sur les 5 pays du MVP avec un bloc `try/except` individuel par pays afin qu'un échec sur un pays n'interrompt pas les autres, et produit un résumé final.

**État actuel de la zone brute** : 313 332 documents répartis sur 5 pays : TGO 47 090, BFA 58 155, NER 68 779, NGA 87 730 et SEN 51 578.

### Phase 4 — Profilage des données et règles métier

#### 4.4 — Profilage multi-pays
Script localisé dans `src/` ou `notebooks/` selon la version, à vérifier avec la commande `find . -name "*profil*"`. Comparaison structurelle des 5 pays en base brute. Les colonnes sont identiques partout, ce qui est positif. Trois divergences réelles ont été découvertes et se révèlent décisives pour la suite :
- **Devises multiples** : XOF pour 4 pays et NGN pour le Nigeria, d'où la nécessité de conserver `price` en devise locale et `usdprice` côte à côte, sans jamais séparer l'un de l'autre.
- **Catégorie non-food** : la colonne `category` contient `non-food` au Nigeria en plus d'un éventail de catégories bien plus large que les autres pays, ce qui reflète une opération du WFP de plus grande ampleur.
- **Pricetype** : la colonne `pricetype` mélange `Retail` et `Wholesale` dans BFA, NER et NGA, alors que le Togo et le Sénégal n'ont que du `Retail`. C'est une dimension à toujours conserver et à ne jamais mélanger dans un même calcul statistique.
- **Priceflag** : au Nigeria, en plus de `actual`, deux valeurs supplémentaires apparaissent : `aggregate` avec 35 180 lignes et `actual,aggregate` avec 1 198 lignes pour cette valeur composite.

#### 4.5 — Investigation empirique du flag aggregate dans notebooks
Aucune documentation officielle et précise du WFP n'a été trouvée pour distinguer `actual` de `aggregate` ; la décision a donc été prise empiriquement. Preuve : des prix identiques au centime près comme "Salt" à 250.0 apparaissent sur 15 à 23 marchés différents à la même date pour les lignes `aggregate`, ce qui est statistiquement impossible pour des observations de terrain indépendantes. Conclusion actée : `aggregate` est une valeur calculée, probablement régionale ou nationale, redistribuée sur plusieurs marchés, et non une observation individuelle fiable. La valeur composite `actual,aggregate` montre un pattern différent où tout un lot marché et date partage ce flag combiné sans cause identifiée avec certitude, mais a été traitée avec la même prudence.

**Décision actée** : seul `priceflag = 'actual'` est utilisé pour la détection d'anomalies. Les autres valeurs restent en base sans aucune suppression mais sont exclues des calculs statistiques via une règle dbt explicite et non un filtre caché.

**Décision actée sur category = 'non-food'** : conservée intacte dans le staging comme réserve pour un futur usage de coût de la vie plus large, mais exclue de la couche intermediate pour le MVP des prix agricoles.

### Phase 5 — Staging PostgreSQL et alimentation ELT

#### 4.6 — Schéma PostgreSQL de staging dans sql/001_create_staging_schema.sql
Table `staging.stg_food_prices`, copie typée et fidèle du brut Mongo sans aucune logique métier, selon le principe ELT. Contrainte d'unicité `UNIQUE` portant sur les colonnes `country_iso3`, `market_id`, `commodity_id`, `price_date` et `pricetype`, définie volontairement sans `priceflag`, pour que la contrainte échoue bruyamment si `actual` et `aggregate` se disputaient un jour la même combinaison. En pratique, aucune violation n'a été constatée lors du chargement réel.

#### 4.7 — Chargement MongoDB vers PostgreSQL dans src/load_staging.py
Script aussi numéroté `09_load_staging.py`. Utilise `psycopg2` au moyen du paquet `psycopg2-binary` et la fonction `execute_values` pour un chargement groupé performant. Idempotent par pays avec un `DELETE` suivi d'un `INSERT`. Un `rollback` système est exécuté en cas d'erreur pour ne pas bloquer les pays suivants sur une connexion en état avorté. **État actuel** : 313 332 lignes chargées dans `staging.stg_food_prices`, avec une correspondance exacte avec MongoDB et sans aucune perte.

### Phase 6 — Modélisation dbt et détection d'anomalies

#### 4.8 — Projet dbt dans veille_prix_dbt
Initialisé avec dbt Core et l'adaptateur `dbt-postgres`, avec pour cible le schéma `dbt_dev` comme environnement de développement. Modèles organisés en 3 couches distinctes : staging, intermediate et marts, selon la convention dbt standard.

- **`models/staging/stg_food_prices.sql`** : lecture fidèle de `staging.stg_food_prices` par la macro source dbt sans aucun filtrage. Déclaration de source dans `models/staging/_sources.yml` avec tests `not_null` sur les colonnes clés et `accepted_values` sur `pricetype`.
- **`models/intermediate/int_food_prices_filtered.sql`** : applique les deux règles métier actées en section 4.5, à savoir `priceflag = 'actual'` et `category != 'non-food'`. Test singulier associé dans `tests/assert_int_food_prices_excludes_non_actual_or_nonfood.sql` vérifiant qu'aucune ligne exclue ne fuite. **Volumétrie résultante : 275 047 lignes** avec TGO, BFA, NER et SEN inchangés, et NGA passant de 87 730 à 49 445.
- **`models/marts/dim_commodities.sql`** : référentiel des commodités avec `commodity_id`, `commodity` et `category`, testé `unique` et validé empiriquement comme identifiant global cohérent entre pays.
- **`models/marts/dim_markets.sql`** : référentiel des marchés avec la clé composite `market_key = country_iso3 || '-' || market_id`. C'est un choix de conception défensif car le `market_id` seul n'est pas garanti unique entre pays, et la composite élimine le risque sans avoir à le prouver.
- **`models/marts/fact_food_prices.sql`** : table de faits référençant `market_key` et `commodity_id`. Tests de relations équivalant à des clés étrangères vérifiés en `PASS` sans aucun fait orphelin.
- **`models/marts/dim_series_eligibility.sql` et `fact_food_prices_eligible.sql`** : décrits en section 4.9.

#### 4.9 — Profilage des séries temporelles et seuil d'éligibilité dans notebooks
Une série représente un triplet composé de `market_key`, `commodity_id` et `pricetype` suivi dans le temps. **4 034 séries distinctes** ont été identifiées, avec une distribution très asymétrique du nombre de points : p25 de 3, médiane de 53, moyenne de 68,2 et maximum de 436. 440 séries n'ont qu'un seul point : 344 sont de jeunes séries démarrées en 2026 qui vont mûrir naturellement, 95 sont des points isolés historiques. Parmi ces points historiques, 82 s'expliquent par 8 dates de campagnes de collecte groupées où un pays entier ou un marché entier est suivi une seule fois puis abandonné, et seulement 13 sont de vraies observations isolées sans pattern, conservées telles quelles car aucune ne semble être une erreur de saisie.

**Décision actée** : seuil d'éligibilité fixé à **12 points minimum**, ce qui correspond à un an d'historique mensuel pour qu'une série soit utilisée en détection d'anomalies. Matérialisé dans `dim_series_eligibility.sql` avec le comptage et le flag `is_eligible`, ainsi que dans `fact_food_prices_eligible.sql` via une jointure filtrée. Test singulier de non-régression associé. **Résultat : 2 616 séries éligibles sur 4 034, soit 64,8%, représentant 211 591 points exploitables.**

#### 4.10 — Détection d'anomalies — méthode choisie et validée sur un cas unique dans notebooks
Méthode : médiane mobile et MAD soit Median Absolute Deviation, z-score modifié avec un facteur d'échelle de 0,6745 selon Iglewicz & Hoaglin 1993, fenêtre glissante de 12 mois et seuil initial de 3,5. Choisie pour sa robustesse aux valeurs extrêmes, contrairement aux méthodes classiques fondées sur la moyenne et l'écart-type. Validée manuellement sur la série la mieux fournie pour le Niger, marché 602, commodité 73, Retail, comptant 436 points de 1990 à 2026. Le mécanisme identifie correctement les ruptures brutales par rapport à une volatilité récente faible, à la hausse comme à la baisse, et non une asymétrie liée à la direction du mouvement comme initialement supposé. Une saisonnalité agricole réelle mais modeste a été confirmée en section 4.11.

#### 4.11 — Généralisation aux 2 616 séries éligibles et test de saisonnalité dans notebooks
Généralisation mécanique de la méthode validée en section 4.10 à toutes les séries éligibles. **Taux d'anomalies obtenu : 10,05%**, soit 21 263 points sur 211 591, considéré comme trop élevé car un seuil à 3,5 écarts-types ne devrait théoriquement cibler qu'environ 0,05% des points sous une distribution normale. Test de saisonnalité par mois calendaire effectué : écart entre le mois le plus bas en mars avec 8,78% et le plus haut en novembre avec 11,77%, soit un ratio de 1,34x statistiquement réel mais d'ampleur pratique faible. L'hypothèse d'une période de soudure de mai à septembre élevée de façon continue est **infirmée à l'échelle agrégée**, juin étant l'un des mois les plus bas. **Décision actée : pas d'ajustement saisonnier explicite pour le MVP**, l'effet étant trop faible pour le justifier.

#### 4.12 — Calibrage du seuil et de la fenêtre — tentative infructueuse dans notebooks
Grille de test sur fenêtre parmi 12, 18 et 24 mois, et seuil parmi 3,5, 5 et 6, calculée sur le **prix brut en niveau absolu**. Les 9 combinaisons restent toutes bien au-dessus d'une cible réaliste de 0,5% à 2%, le meilleur cas avec une fenêtre de 24 et un seuil de 6 conservant encore 3,71%. **Diagnostic** : le problème n'est pas un mauvais calibrage mais le signal lui-même. Mesurer l'écart sur le prix brut absolu mélange tendance longue, saisonnalité et chocs, qu'aucun couple fenêtre et seuil ne peut démêler proprement.

#### 4.13 — Test de variation mois sur mois dans notebooks/13_2_calibration2.py
Changement de signal : détection appliquée sur le taux de variation mensuel calculé par `prix_t / prix_t-1 - 1` plutôt que sur le prix brut, avec la même méthode MAD et z-score, une fenêtre de 12 et un seuil de 3,5. **Résultat : 7,98%**, soit 16 574 anomalies sur 207 604 points. C'est une amélioration réelle par rapport aux 10,05% du prix brut, mais cela reste **loin de la cible de 0,5% à 2%**. Ce résultat a motivé l'abandon définitif de l'approche MAD et z-score au profit des percentiles comme détaillé dans les sections 4.14 à 4.16.

#### 4.14 — Profilage pré-implémentation percentile dans notebooks/14_profil_avant_percentile.py
Avant d'écrire le modèle dbt, profilage complet de la distribution des variations mois sur mois. Résultats clés :
- Zéro valeur infinie sans aucun `price_t-1` égal à 0 et zéro variation à -100% sans aucun prix tombant à 0 : données propres sur ce point.
- 67 groupes formés par `commodity_id` et `pricetype`, taille médiane de 1 237 points par groupe avec un p25 de 678 et un maximum de 44 792, ce qui est très confortable pour des percentiles stables.
- 4 groupes sous 50 points dont 3 groupes sous la barre de 30 : seuil `min_n_group = 30` acté pour exclure les percentiles non fiables.
- Simulation préalable : taux attendu de **1,99%** avec P01 et P99, conforme à la cible avant même d'écrire le SQL.

#### 4.15 — Investigation des groupes suspects dans notebooks/15_investigate_suspects.py
8 groupes présentaient des seuils extrêmes avec un P01 inférieur à -80% ou un P99 supérieur à +300%. Investigation empirique cas par cas :
- **Lait en poudre Nigeria commodité 238** : hausse de +3025% en mai 2022 suite à la crise monétaire au Nigeria en 2022. C'est un choc NGN réel et non un artéfact, flagué à juste titre.
- **Cowpeas brown Wholesale Nigeria commodité 480** : hausse de +9211% en janvier 2019 sur `NGA-1971` passant de 216 NGN à 19 400 NGN. C me artéfact probable dû à un changement d'unité NGN. Mais le P99 du groupe à 3,15 n'est pas faussé par cet outlier extrême et la valeur à 92x est elle-même flagguée comme anomalie, ce qui confirme un comportement correct.
- **Épinards, bananes, oranges et poisson Nigeria** : saisonnalité forte sur les produits frais avec un pattern de chutes et hausses brutales entre saisons. C'est un signal économique réel et non des artéfacts.
- **Décision actée** : pas de tronquage des variations extrêmes. Les chocs réels et les artéfacts doivent tous être flagués sans être masqués dans les seuils.

#### 4.16 — Validation finale anti-écatombe et matérialisation dbt dans notebooks/16_validation_finale_percentile.py
Validation exhaustive avant implémentation : contrôle que le taux global de 1,99% ne cache pas une distribution pathologique sur un sous-ensemble.

**Résultats des contrôles anti-écatombe** :

| Dimension | Taux max observé | Seuil d'alerte | Résultat |
|---|---|---|---|
| Pays | NGA 2,96% / TGO 2,86% | Supérieur à 10% | ✅ |
| Catégorie de commodité | Huiles 2,09% | Supérieur à 10% | ✅ |
| Commodité individuelle | Wheat Wholesale 4,17% avec n=48 | Supérieur à 15% | ✅ |
| Temporel | 1996 : 5,67% / 2005 : 6,64% | Supérieur à 5% = choc réel | ✅ cohérent |

Les années à taux élevé comme 1996, 2005 et 2022 correspondent à des crises économiques documentées et non à un bug.

**Modèle dbt livré** : `models/marts/fact_food_prices_anomalies.sql` matérialisé sous forme de table. Colonnes ajoutées par rapport à `fact_food_prices_eligible` : `pct_change`, `threshold_p01`, `threshold_p99`, `n_group_for_threshold`, `is_anomaly` de type BOOLEAN non NULL, `anomaly_direction` prenant les valeurs `hausse`, `baisse`, `normal` ou `non_evalue`, et `anomaly_severity` mesurant la distance au seuil dépassé.

**Test singulier de garde-fou** : `tests/assert_anomaly_rate_in_bounds.sql` — échoue si le taux global sort des bornes de 0,5% à 5,0% ou si la table contient moins de 100 000 points, afin de se protéger contre un bug silencieux qui viderait la table.

**Execution dbt build complète : 49/49 PASS, WARN=0, ERROR=0.** Commit `fb062e4`.

### Phase 7 — Orchestration Airflow

#### 4.17 — Installation d'Airflow
Airflow 3.3.1 installé dans le même environnement virtuel `.venv` que dbt sous Python 3.12.3, via le fichier de contraintes officiel résolu dynamiquement contre PyPI. L'outil `pip` a signalé un conflit de versions transitives pour `pathspec` et `more-itertools` entre les dépendances d'Airflow et celles de `dbt-common` et `metricflow`. Vérifié empiriquement avant d'agir selon la convention 6 : un `dbt build` complet a été rejoué avec un résultat 49/49 PASS identique à la référence de la Phase 6 au commit `fb062e4`, et la volumétrie de `fact_food_prices_anomalies` est restée inchangée à 270 861 lignes. **Décision actée** : le conflit est traité comme un faux positif car `dbt-common` et `metricflow` portent le Semantic Layer dbt non utilisé dans ce projet, donc leurs bornes de version n'affectent pas les commandes réellement exécutées. Un seul `.venv` est conservé pour tout le projet sans scission entre dbt et Airflow. À re-vérifier si dbt ou Airflow est mis à jour ultérieurement.

#### 4.18 — Emplacement des DAGs
Par défaut, Airflow cherche les DAGs dans `$AIRFLOW_HOME/dags`, or le dossier `airflow_home/` est entièrement exclu du versioning car il constitue un état runtime local. Décision : le dossier `dags/` a été créé à la racine du dépôt pour être versionné, et Airflow a été pointé dessus via l'instruction `export AIRFLOW__CORE__DAGS_FOLDER="$PWD/dags"`. Ce mécanisme a été validé avec un DAG minimal nommé `test_setup_veille_prix`, déclenché manuellement avec succès. **Point de vigilance non résolu** : cet export ainsi que `AIRFLOW_HOME` ne sont pas persistants et doivent être réexécutés à chaque nouvelle session shell tant qu'aucun script de démarrage n'est mis en place. À adresser si la friction devient réelle sans céder à la sur-ingénierie prématurée.

#### 4.19 — Pipeline complet Airflow
DAG `veille_prix_pipeline` défini dans `dags/veille_prix_pipeline.py`, comprenant 3 tâches séquentielles : `ingestion_multi_pays` via `06_multiingest.py`, `chargement_staging` via `09_load_staging.py` et `dbt_build` via `dbt build`. Chaque script Python porte un garde-fou explicite déclenchant un arrêt avec le code d'erreur 1 si un pays échoue afin qu'Airflow détecte un échec partiel silencieux. La tâche `dbt build` s'appuie nativement sur son propre code de sortie sans nécessiter de garde-fou sur mesure. Validation empirique de bout en bout : exécution manuelle complète avec 3 tâches sur 3 validées, 318 016 lignes ingérées et chargées en staging, et un code de sortie 0 pour `dbt build`. La planification est définie à `@monthly` avec `catchup=False`.
**Point de vigilance non résolu** : les variables `AIRFLOW_HOME` et `AIRFLOW__CORE__DAGS_FOLDER` doivent être exportées à chaque session, et rien ne garantit que le scheduler tourne en continu pour honorer l'intervalle mensuel automatiquement, ce qui reste à traiter dans une phase ultérieure.

### Phase 8 — Conteneurisation Docker Compose

#### 4.22 — Postgres conteneurisé et validé en isolement
Définition dans `docker-compose.yml` du service `postgres` s'appuyant sur l'image `postgres:16-alpine` alignée sur la version native 16.14, avec le port hôte `5434`. Un volume nommé `postgres_data` assure la persistance. Validation : conteneur à l'état `Up`, connexion `psql` réussie avec les identifiants du compose et base neuve confirmée vide. Prochaine étape : conteneurisation de MongoDB puis mise en réseau des deux services avec adaptation des scripts, les paramètres `PG_DSN` et `MONGO_URI` étant actuellement en dur sur `localhost` avec l'authentification Postgres native en peer et trust.

#### 4.23 — MongoDB conteneurisé et validé en isolement
Service `mongo` ajouté au `docker-compose.yml` avec l'image officielle `mongo:8.0`. Aucune déclinaison alpine n'est disponible officiellement pour Mongo suite au retrait de licence par Alpine et aux alternatives communautaires non maintenues. Port hôte choisi après vérification des ports déjà occupés sur la machine en raison de plusieurs projets Docker actifs en parallèle. Validation : conteneur à l'état `Up`, connexion `mongosh` authentifiée réussie et commande `show dbs` confirmant une instance neuve avec uniquement `admin`, `config` et `local`, sans la base `veille_prix_agricoles`.

### Phase 10 — Dashboard de reporting Streamlit

#### 4.20 — Dashboard Streamlit
Dashboard de reporting final construit dans `dashboard/app.py` et lancé via `streamlit run dashboard/app.py`. Thème Streamlit configuré dans `.streamlit/config.toml`. Trois dépendances ajoutées au `requirements.txt` avec versions épinglées selon l'installation réelle : `streamlit==1.61.1`, `plotly==6.9.0` et `pydeck==0.9.3`.

**Schéma et tables utilisés** : `dbt_dev`, qui est la seule cible configurée dans `profiles.yml` sans schéma de production distinct. Tables et vues interrogées : `dbt_dev.fact_food_prices_anomalies` comme table matérialisée et source principale comptant 275 137 lignes et 16 colonnes, `dbt_dev.dim_commodities` comme vue avec `commodity_id`, `commodity` et `category`, et `dbt_dev.dim_markets` comme vue avec `market_key`, `country_iso3`, `market`, `admin1`, `latitude` et `longitude`. La jointure est systématiquement réalisée côté SQL entre `fact_food_prices_anomalies` et les deux dimensions pour obtenir des noms lisibles.

**Coordonnées géographiques** : vérifiées empiriquement, 100% des marchés soit 367 marchés sur 367 à travers 5 pays possèdent une latitude et une longitude renseignées. La carte est donc pleinement fonctionnelle sans estimation ni géocodage externe.

**Connexion PostgreSQL** : `PG_DSN = "dbname=veille_prix_agricoles"`, en cohérence avec `src/09_load_staging.py` et `profiles.yml` avec hôte localhost, port 5432 et utilisateur broly. Aucun identifiant n'est codé en dur dans le dashboard et `psycopg2` utilise l'authentification peer du système.

**Décisions de design** :
- Palette : `#D846E5` en magenta pour le signal d'anomalie uniquement, `#214B1B` en vert foncé pour la structure et le texte, `#F0EEE2` en crème pour les surfaces de données. Aucune couleur hors palette.
- Typographie : Lora en font serif dominante, et Source Code Pro en monospace pour les données numériques et les contrôles d'interface. Ce choix est justifié par l'alignement naturel des colonnes de chiffres et le contraste visuel entre le récit et la donnée brute.
- Élément signature : bande de sévérité représentée par une barre horizontale pleine largeur sous le titre. Chaque segment représente une anomalie du mois le plus récent, ordonnée par sévérité croissante selon un gradient vert foncé vers magenta. C'est un objet visuel unique ancré dans le sujet pour transmettre le pouls de la sécurité alimentaire.
- Structure en trois actes : Acte I pour localiser les anomalies avec narration, carte et barres par pays ; Acte II pour identifier les denrées et la dynamique avec le top 15 et l'évolution temporelle des hausses et baisses ; Acte III pour le détail filtrable sous forme de tableau avec filtres par pays, direction et période.
- Carte : carte Plotly Scattermap en style carto-positron. Tous les marchés sont représentés en points discrets vert foncé et les marchés avec des anomalies récentes sur 3 mois apparaissent en magenta avec une taille proportionnelle au nombre d'anomalies.
- Narration automatique : bloc de texte identifiant l'anomalie la plus sévère du mois le plus récent, formulée en langage décisionnel indiquant que ce mouvement fait partie des 2% les plus extrêmes jamais observés pour cette denrée.
- Aucun émoji dans l'interface et aucune animation.

**Volumétrie réelle affichée** : 275 137 points analysés, 5 432 anomalies détectées soit 1,97%, 5 pays, 50 denrées, 281 marchés et des données allant de 1990 à juin 2026. La légère différence avec les 270 861 lignes et 5 331 anomalies documentées en section 4.16 est cohérente avec la nouvelle exécution d'Airflow de la section 4.19 ayant ingéré un lot plus récent de 318 016 lignes en staging contre 313 332 précédemment.

## 5. Décisions de conception actées — résumé consolidé

| # | Décision | Statut |
|---|---|---|
| 1 | Conserver `price` en devise locale et `usdprice` en permanence, sans jamais séparer l'un de l'autre | Actée, implémentée |
| 2 | Maintenir `pricetype` comprenant Retail et Wholesale comme une dimension explicite sans la mélanger dans les calculs | Actée, implémentée |
| 3 | Seul `priceflag='actual'` est fiable pour les statistiques ; `aggregate` est conservé en base mais exclu en aval | Actée, implémentée en couche intermediate |
| 4 | La catégorie `non-food` est conservée en réserve dans le staging et exclue du MVP en aval | Actée, implémentée |
| 5 | Périmètre géographique fixé sur la norme UN M49 Afrique de l'Ouest couvrant 16 pays et non la CEDEAO | Actée |
| 6 | Périmètre MVP établi sur 5 pays soit TGO, BFA, NER, NGA et SEN ; 4 pays supplémentaires identifiés mais non ingérés soit GHA, BEN, MLI et CIV | Actée |
| 7 | Clé `market_key` composite associant le pays et le market_id selon une conception défensive à coût nul | Actée, implémentée |
| 8 | Seuil d'éligibilité statistique fixé à 12 points minimum par série | Actée, implémentée |
| 9 | Méthode d'anomalie basée sur les percentiles P01 et P99 par groupe commodité et type sur la variation mensuelle | Actée, implémentée en remplacement de la méthode MAD et z-score abandonnée |
| 10 | Absence d'ajustement saisonnier explicite pour le MVP | Actée |
| 11 | Signal basé sur la variation mensuelle de `price` en devise locale et non sur `usdprice` | Actée, implémentée pour éviter les faux positifs liés à la dévaluation NGN |
| 12 | Groupes ayant moins de 30 points de variation évaluable exclus du flaggage avec `min_n_group = 30` dans le SQL | Actée, implémentée pour éviter les seuils percentiles non fiables |
| 13 | Pas de tronquage des variations extrêmes avant le calcul des percentiles | Actée afin que les chocs réels et artéfacts soient flagués sans être masqués |

## 6. État des données à date

- Zone brute MongoDB `veille_prix_agricoles.raw_food_prices` : 313 332 documents sur 5 pays.
- Staging PostgreSQL `staging.stg_food_prices` : 313 332 lignes, en correspondance exacte avec Mongo.
- dbt intermediate `dbt_dev.int_food_prices_filtered` : 275 047 lignes après le filtrage de qualité.
- dbt marts — faits éligibles `dbt_dev.fact_food_prices_eligible` : 270 861 lignes et 2 616 séries éligibles sur un total de 4 034 séries.
- dbt marts — anomalies `dbt_dev.fact_food_prices_anomalies` : **270 861 lignes**, **5 331 anomalies détectées soit 1,99%**, réparties en 2 675 hausses représentant 1,00% et 2 656 baisses représentant 0,99%. Table matérialisée avec `dbt build` validé 49/49 PASS.

**Répartition des anomalies par pays** : BFA 1,07% — NER 1,72% — NGA 2,96% — SEN 1,70% — TGO 2,86%. Aucun pays ni aucune catégorie ne dépasse 10%, ce qui valide le contrôle anti-écatombe.

## 7. ~~Problème non résolu~~ → Résolu en Phase 6

Le calibrage MAD et z-score avait échoué à atteindre la cible, le meilleur résultat étant 7,98% avec le signal de variation mois sur mois. **L'approche par percentile non-paramétrique a résolu le problème**, comme détaillé dans les sections 4.14 à 4.16 :

- Signal : variation mensuelle sur `price` en devise locale
- Seuils : P01 et P99 calculés par groupe sur `commodity_id` et `pricetype`
- Résultat obtenu : **1,99%** — situé dans la cible de 0,5% à 2%, de manière symétrique avec 1,00% de hausses et 0,99% de baisses
- Matérialisé en `dbt_dev.fact_food_prices_anomalies`, testé et validé

**Formulation pour le reporting en Phase 10** : "ce mouvement de prix fait partie des 2% les plus extrêmes jamais observés pour cette denrée". C'est un message naturel pour un décideur non technique, bien plus parlant qu'un z-score abstrait.

## 8. Feuille de route restante — directives par phase

### ~~Phase 6~~ ✅ CLÔTURÉE — Détection d'anomalies
Implémentée via percentiles P01 et P99 par groupe commodité et type. Modèle `models/marts/fact_food_prices_anomalies.sql` matérialisé en table. Test de garde-fou `tests/assert_anomaly_rate_in_bounds.sql` validé sur la plage 0,5% à 5,0%. Execution `dbt build` 49/49 PASS sous le commit `fb062e4`. Consulter les sections 4.14 à 4.16 pour le détail complet.

### Phase 7 — Orchestration Airflow
Un seul DAG avec la séquence : ingestion multi-pays → chargement staging → `dbt build` sur toutes les couches → régénération optionnelle d'un export de reporting. Fréquence mensuelle alignée sur la cadence de mise à jour de la source HDX, confirmée en Mission 2 comme récente à quelques jours près. Ne pas complexifier avec plusieurs DAGs pour un MVP — un seul pipeline linéaire suffit et se défend mieux en entretien qu'une orchestration sur-conçue.

### Phase 8 — Docker Compose
Conteneuriser pour la reproductibilité avec Postgres, MongoDB, Airflow et éventuellement Metabase. Contrainte forte : budget disque partagé avec d'autres projets à hauteur d'environ 25 Go au total. Il convient d'utiliser des images officielles allégées avec les tags `-slim` ou `-alpine` quand disponible, et de ne pas dupliquer les services déjà natifs pendant le développement. Le mode natif reste la référence de dev et Docker Compose constitue le livrable de reproductibilité finale.

### Phase 9 — CI/CD GitHub Actions
Un seul workflow : lint Python via ruff ou flake8, suivi de `dbt compile` et `dbt test` contre un service PostgreSQL éphémère en CI. Ne pas viser un pipeline multi-étapes élaboré — l'objectif est de démontrer la compétence CI/CD sans construire une usine à gaz pour un projet solo.

### Phase 10 — Reporting et storytelling
Priorité forte, c'est la partie la plus visible du projet. Recommandation d'outil : **Streamlit** pour un contrôle total sur la narration et le code Python déjà maîtrisé sur ce projet, plutôt que Metabase qui est plus générique et offre moins de contrôle narratif, sauf si l'agent identifie une contrainte qui justifie l'inverse.

**Directives de contenu pour réduire la charge cognitive du décideur** :
- La vue par défaut doit répondre à 3 questions, dans cet ordre :
  1. *Où est-ce anormal maintenant ?* — affichage d'une liste courte des anomalies les plus récentes et les plus sévères, sans montrer les 2 616 séries d'un coup.
  2. *Est-ce ponctuel ou une tendance installée ?* — contexte visuel avec graphique de prix et médiane mobile pour chaque anomalie affichée.
  3. *Que faire concrètement ?* — liste actionnable avec marché, commodité et pays, au-delà d'un simple graphique agrégé.
- Utiliser un code couleur simple de type feu tricolore pour la sévérité plutôt que des valeurs statistiques brutes affichées en premier plan.
- Transmettre un seul message clé par visuel — éviter les tableaux de bord denses en première vue, et permettre le drill-down vers le détail plutôt que tout montrer d'emblée.
- S'appuyer sur le vocabulaire de percentile recommandé en section 7 pour formuler les messages, tel que "parmi les 2% de mouvements les plus extrêmes", ce qui est plus parlant qu'un z-score pour un public non technique.

### Phase 11 — Documentation et préparation entretien
Fichier README public reconstruit à partir de ce document sous forme de version condensée orientée pour un lecteur externe plutôt que pour un agent IA. Documenter explicitement le parcours d'investigation qualité couvert dans les sections 4.5, 4.9, 4.12 et 4.13 de ce document. **C'est une valeur ajoutée du projet en soi**, à ne pas résumer en une ligne : la rigueur de découverte de `aggregate`, du seuil d'éligibilité, et l'échec puis la correction du calibrage sont exactement le genre de récit qui démontre une compétence Data Analytics en entretien, davantage qu'un dashboard fini sans le raisonnement derrière.

**Tâche annexe de priorité basse** : étendre l'ingestion aux 4 pays déjà identifiés soit GHA, BEN, MLI et CIV. C'est une extension triviale du dictionnaire de configuration existant sans aucun nouveau code requis. À faire seulement une fois les phases 6 à 10 stabilisées, jamais avant.

## 9. Principes de raisonnement à reproduire

Ce projet a été construit avec une discipline précise, à maintenir pour rester cohérent avec ce qui précède :

1. **Ne jamais deviner une donnée externe telle qu'une URL, une définition ou une structure — toujours vérifier**, par recherche puis par preuve empirique sur les données réelles. Une hypothèse non vérifiée reste une hypothèse et n'est jamais actée comme un fait.
2. **Profiler avant de concevoir.** Chaque schéma, chaque seuil et chaque règle de filtrage de ce projet a été précédé d'un script d'exploration sur les données réelles — sans jamais déduire uniquement de la documentation ou de l'intuition.
3. **MVP avant généralisation.** Valider un mécanisme sur un cas unique comme un pays ou une série avant de l'appliquer à l'échelle. Garder une configuration extensible en réserve telle que le dictionnaire à 9 pays sans la déployer avant que le socle soit prouvé.
4. **Documenter la décision et sa raison, pas seulement le résultat.** Chaque choix de ce document à la section 5 porte sa justification : un agent qui reprend le projet doit pouvoir comprendre la raison sous-jacente et non seulement appliquer la consigne.
5. **Séparer le brut, le typé et le métier.** La discipline staging, intermediate et marts n'est pas une convention arbitraire — elle garantit qu'une donnée brute reste toujours récupérable même si une règle métier s'avère erronée plus tard.
6. **Livrer de la valeur sans s'éparpiller dans la calibration infinie.** Leçon tirée en Phase 6 : quand une itération de calibrage n'a pas convergé après 2 ou 3 tentatives raisonnables, changer d'approche plutôt que de multiplier les variantes du même réglage. La solution percentile a rompu délibérément avec la boucle MAD et z-score plutôt que de la poursuivre, et a atteint la cible dès la première implémentation.
7. **Chaque commit correspond à une unité de travail complète et testée**, et non à un état intermédiaire cassé — vérifier `git status` puis `dbt build` et les tests avant de committer.

---

*Fin du document de passation. Toute reprise du projet doit commencer par la commande `find . -name "*.py" -o -name "*.sql"` en excluant les dossiers ignorés pour confirmer l'inventaire exact des fichiers avant de s'appuyer sur les chemins mentionnés ci-dessus.*