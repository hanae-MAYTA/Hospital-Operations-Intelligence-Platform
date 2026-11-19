"""
Étape EXTRACT : lit les fichiers CSV bruts de data/raw/.
Vérifie que chaque fichier existe et n'est pas vide, puis logue le nombre de lignes lues.
Aucune modification des données ici : on lit "tel quel".

Auteures : Hanae MAYTA et Wafae ZALOUK
"""
from pathlib import Path

import pandas as pd

from src.config import RAW_DIR, RAW_FILES, get_logger

log = get_logger("extract")


class ExtractError(Exception):
    """Erreur levée quand un fichier source est absent ou vide."""


def read_csv_file(path: Path) -> pd.DataFrame:
    """Lit un CSV en gardant toutes les colonnes en texte (le nettoyage se fait dans Transform)."""
    if not path.exists():
        raise ExtractError(f"Fichier introuvable : {path}. Lancez d'abord `make data`.")
    df = pd.read_csv(path, dtype=str, keep_default_na=True)
    if df.empty:
        raise ExtractError(f"Fichier vide : {path}")
    log.info("%-12s : %6d lignes lues (%d colonnes)", path.stem, len(df), df.shape[1])
    return df


def extract(raw_dir: Path = RAW_DIR) -> dict[str, pd.DataFrame]:
    """Lit les 4 fichiers sources et les retourne dans un dictionnaire {nom: DataFrame}."""
    log.info("EXTRACT - lecture des fichiers dans %s", raw_dir)
    return {name: read_csv_file(Path(raw_dir) / f"{name}.csv") for name in RAW_FILES}
