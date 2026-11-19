"""
DAG Airflow : automatise la pipeline hospitalière chaque jour à 02:00.
extract >> transform >> validate >> load >> quality_check, avec 2 nouvelles tentatives
en cas d'échec. Chaque tâche appelle une fonction de src/pipeline.py (même code que sans Airflow).

Auteures : Hanae MAYTA et Wafae ZALOUK
"""
import sys
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator

sys.path.insert(0, "/opt/project")  # le dossier du projet est monté ici par docker-compose

from src.pipeline import (  # noqa: E402
    step_extract, step_load, step_quality_check, step_transform, step_validate,
)

default_args = {
    "owner": "hanae_wafae",
    "retries": 2,                          # 2 nouvelles tentatives si une tâche échoue
    "retry_delay": timedelta(minutes=5),
}

with DAG(
    dag_id="hospital_etl_pipeline",
    description="CSV hospitaliers -> nettoyage -> contrôles qualité -> PostgreSQL (schéma en étoile)",
    default_args=default_args,
    start_date=datetime(2024, 1, 1),
    schedule="0 2 * * *",                  # tous les jours à 02:00
    catchup=False,                         # on ne rejoue pas les jours passés
    tags=["hospital", "etl"],
) as dag:
    extract = PythonOperator(task_id="extract", python_callable=step_extract)
    transform = PythonOperator(task_id="transform", python_callable=step_transform)
    validate = PythonOperator(task_id="validate", python_callable=step_validate)
    load = PythonOperator(task_id="load", python_callable=step_load)
    quality_check = PythonOperator(task_id="quality_check", python_callable=step_quality_check)

    extract >> transform >> validate >> load >> quality_check
