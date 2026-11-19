"""
Étape LOAD : charge les tables nettoyées dans PostgreSQL (schéma en étoile).
Le chargement est IDEMPOTENT : on passe par une table temporaire puis
INSERT ... ON CONFLICT DO UPDATE (upsert). Relancer la pipeline ne crée donc aucun doublon.

Auteures : Hanae MAYTA et Wafae ZALOUK
"""
import pandas as pd
from sqlalchemy import text

from src.config import SQL_DIR, get_engine, get_logger

log = get_logger("load")

# Ordre important : les dimensions avant la table de faits (clés étrangères)
LOAD_ORDER = ["dim_department", "dim_patient", "dim_date", "dim_staff", "fact_admission"]
PRIMARY_KEYS = {"dim_patient": "patient_id", "dim_department": "department_id",
                "dim_staff": "staff_id", "dim_date": "date_id", "fact_admission": "admission_id"}


def run_sql_file(engine, filename: str) -> None:
    """Exécute un fichier SQL du dossier sql/ (création du schéma, vues...)."""
    sql = (SQL_DIR / filename).read_text(encoding="utf-8")
    with engine.begin() as conn:
        conn.exec_driver_sql(sql)
    log.info("Script SQL exécuté : %s", filename)


def get_column_types(conn, table: str) -> dict[str, str]:
    """Lit le type SQL de chaque colonne de la table cible (pour convertir la table temporaire)."""
    rows = conn.execute(text(
        "SELECT column_name, data_type FROM information_schema.columns "
        "WHERE table_name = :t AND table_schema = current_schema()"
    ), {"t": table})
    return {name: dtype for name, dtype in rows}


def upsert_table(conn, df: pd.DataFrame, table: str) -> int:
    """Insère ou met à jour les lignes de `df` dans `table` sans créer de doublons."""
    staging = f"stg_{table}"
    df.to_sql(staging, conn, if_exists="replace", index=False, method="multi", chunksize=2000)

    types = get_column_types(conn, table)
    pk = PRIMARY_KEYS[table]
    columns = [c for c in df.columns if c in types]
    select = ", ".join(f'CAST("{c}" AS {types[c]})' for c in columns)
    updates = ", ".join(f'"{c}" = EXCLUDED."{c}"' for c in columns if c != pk)
    conn.execute(text(f"""
        INSERT INTO {table} ({", ".join(f'"{c}"' for c in columns)})
        SELECT {select} FROM {staging}
        ON CONFLICT ("{pk}") DO UPDATE SET {updates}
    """))
    conn.execute(text(f"DROP TABLE {staging}"))
    return len(df)


def load(tables: dict[str, pd.DataFrame], engine=None) -> int:
    """Crée le schéma si besoin puis charge toutes les tables dans une seule transaction."""
    log.info("LOAD - chargement dans PostgreSQL")
    engine = engine or get_engine()
    run_sql_file(engine, "01_create_schema.sql")

    total = 0
    with engine.begin() as conn:  # tout ou rien : en cas d'erreur, rien n'est chargé
        for table in LOAD_ORDER:
            n = upsert_table(conn, tables[table], table)
            log.info("%-15s : %6d lignes chargées (upsert)", table, n)
            total += n
    run_sql_file(engine, "03_views_powerbi.sql")
    return total


def log_pipeline_run(status: str, rows: int, duration: float, message: str = "", engine=None) -> None:
    """Enregistre l'exécution dans la table pipeline_runs (succès ou échec)."""
    try:
        engine = engine or get_engine()
        run_sql_file(engine, "01_create_schema.sql")
        with engine.begin() as conn:
            conn.execute(text(
                "INSERT INTO pipeline_runs (status, rows_loaded, duration_seconds, message) "
                "VALUES (:s, :r, :d, :m)"
            ), {"s": status, "r": rows, "d": round(duration, 2), "m": message[:500]})
    except Exception as exc:  # la base peut être indisponible : on ne masque pas l'erreur d'origine
        log.warning("Impossible d'écrire dans pipeline_runs : %s", exc)
