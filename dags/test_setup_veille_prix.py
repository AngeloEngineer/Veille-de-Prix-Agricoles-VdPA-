from datetime import datetime
from airflow.sdk import dag, task

@dag(
    dag_id="test_setup_veille_prix",
    schedule=None,
    start_date=datetime(2026, 8, 15),
    catchup=False,
    tags= ['setup', 'test']
)

def test_setup():
    @task
    def hello():
        print("Veille Prix Agricoles - mécanisme DAG OK")
        return "OK"

    hello()

test_setup()