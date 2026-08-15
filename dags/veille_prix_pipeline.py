from pathlib import Path
from datetime import datetime
from airflow.sdk import dag
from airflow.providers.standard.operators.bash import BashOperator

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PYTHON_BIN = PROJECT_ROOT / ".venv" / "bin" / "python"

@dag(
    dag_id="veille_prix_pipeline",
    schedule="@monthly",
    start_date=datetime(2026, 8, 15),
    catchup=False,
    tags=["veille-prix", "production"],
)

def veille_prix_pipeline():
    ingestion =BashOperator(
        task_id="ingestion_multi_pays",
        bash_command=f"{PYTHON_BIN} {PROJECT_ROOT / 'src' / '06_multiingest.py'}",
        cwd=str(PROJECT_ROOT),     
    )

    chargement_staging = BashOperator(
    task_id="chargement_staging",
    bash_command=f"{PYTHON_BIN} {PROJECT_ROOT / 'src' / '09_load_staging.py'}",
    cwd=str(PROJECT_ROOT),
    )

    dbt_build = BashOperator(
        task_id="dbt_build",
        bash_command=f"{PROJECT_ROOT / '.venv' / 'bin'/ 'dbt'} build",
        cwd=str(PROJECT_ROOT / "veille_prix_dbt"), 
    )

    ingestion >> chargement_staging >> dbt_build

veille_prix_pipeline()
