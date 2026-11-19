"""
Orchestrateur de la pipeline : Extract -> Transform -> Validate -> Load -> Quality check.
Mesure le temps de chaque étape, logue tout, et enregistre l'exécution dans pipeline_runs.
Se lance SANS Airflow avec : python -m src.pipeline
Démo d'échec : python -m src.pipeline --simulate-bad-data (injecte une attente négative)

Auteures : Hanae MAYTA et Wafae ZALOUK
"""
import argparse
import pickle
import sys
import time

from sqlalchemy import text

from src.config import INTERIM_DIR, PROCESSED_DIR, get_engine, get_logger
from src.extract import extract
from src.load import load, log_pipeline_run
from src.transform import transform
from src.validate import validate

log = get_logger("pipeline")


# ---------- Petits utilitaires ----------

def save_interim(obj, name: str) -> None:
    """Sauvegarde un résultat intermédiaire (utile pour Airflow : 1 tâche = 1 processus)."""
    INTERIM_DIR.mkdir(parents=True, exist_ok=True)
    with open(INTERIM_DIR / f"{name}.pkl", "wb") as f:
        pickle.dump(obj, f)


def read_interim(name: str):
    """Relit un résultat intermédiaire écrit par la tâche précédente."""
    with open(INTERIM_DIR / f"{name}.pkl", "rb") as f:
        return pickle.load(f)


def save_processed(tables: dict) -> None:
    """Écrit les tables propres en CSV dans data/processed/."""
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    for name, df in tables.items():
        df.to_csv(PROCESSED_DIR / f"{name}.csv", index=False)
    log.info("Tables propres écrites dans %s", PROCESSED_DIR)


def quality_check(tables: dict, engine=None) -> None:
    """Contrôle APRÈS chargement : la base contient bien les mêmes volumes, sans doublon."""
    engine = engine or get_engine()
    with engine.connect() as conn:
        for name, df in tables.items():
            in_db = conn.execute(text(f"SELECT COUNT(*) FROM {name}")).scalar()
            if in_db < len(df):
                raise RuntimeError(f"{name} : {in_db} lignes en base, {len(df)} attendues")
        dup = conn.execute(text(
            "SELECT COUNT(*) - COUNT(DISTINCT admission_id) FROM fact_admission")).scalar()
        if dup:
            raise RuntimeError(f"{dup} doublon(s) dans fact_admission après chargement")
    log.info("QUALITY CHECK - volumes en base conformes, aucun doublon ✅")


# ---------- Tâches individuelles (appelées par le DAG Airflow) ----------

def step_extract() -> None:
    save_interim(extract(), "raw")


def step_transform() -> None:
    tables, stats = transform(read_interim("raw"))
    save_processed(tables)
    save_interim((tables, stats), "clean")


def step_validate() -> None:
    tables, stats = read_interim("clean")
    validate(tables, stats)


def step_load() -> None:
    start = time.time()
    tables, _ = read_interim("clean")
    rows = load(tables)
    log_pipeline_run("SUCCESS", rows, time.time() - start, "Chargement via Airflow")


def step_quality_check() -> None:
    tables, _ = read_interim("clean")
    quality_check(tables)


# ---------- Exécution complète (sans Airflow) ----------

def timed(label: str, func, *args):
    """Exécute une étape et logue sa durée."""
    start = time.time()
    result = func(*args)
    log.info("⏱  %-10s terminé en %.2f s", label, time.time() - start)
    return result


def corrupt_for_demo(tables: dict) -> None:
    """DÉMO : abîme volontairement 3 lignes APRÈS Transform pour montrer que Validate bloque."""
    log.warning("⚠️  MODE DÉMO : 3 temps d'attente négatifs injectés après Transform")
    tables["fact_admission"].loc[:2, "waiting_time"] = -30


def run_pipeline(simulate_bad_data: bool = False) -> int:
    """Lance toute la pipeline. Retourne le nombre de lignes chargées."""
    start = time.time()
    log.info("=" * 60)
    log.info("DÉMARRAGE DE LA PIPELINE - Hospital Operations Intelligence Platform")
    log.info("=" * 60)
    try:
        raw = timed("Extract", extract)
        tables, stats = timed("Transform", transform, raw)
        save_processed(tables)
        if simulate_bad_data:
            corrupt_for_demo(tables)
        timed("Validate", validate, tables, stats)
        rows = timed("Load", load, tables)
        timed("Quality", quality_check, tables)
    except Exception as exc:
        duration = time.time() - start
        log.error("❌ PIPELINE EN ÉCHEC après %.2f s : %s", duration, exc)
        log_pipeline_run("FAILED", 0, duration, str(exc))
        raise
    duration = time.time() - start
    log_pipeline_run("SUCCESS", rows, duration, "Exécution complète")
    log.info("✅ PIPELINE TERMINÉE : %d lignes chargées en %.2f s", rows, duration)
    return rows


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pipeline ETL hospitalière")
    parser.add_argument("--simulate-bad-data", action="store_true",
                        help="injecte des données invalides pour montrer l'arrêt de la pipeline")
    try:
        run_pipeline(parser.parse_args().simulate_bad_data)
    except Exception:
        sys.exit(1)
