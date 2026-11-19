"""
Configuration centralisée du projet Hospital Operations Intelligence Platform.
Lit les variables du fichier .env (connexion PostgreSQL, seuils de qualité, clé API)
et définit les chemins utilisés par toutes les étapes de la pipeline.

Auteures : Hanae MAYTA et Wafae ZALOUK
"""
import logging
import os
from pathlib import Path

from dotenv import load_dotenv

# Racine du projet (le dossier qui contient src/)
ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")

# --- Chemins ---
SOURCE_DIR = ROOT_DIR / "data" / "source"        # dataset Kaggle d'origine
RAW_DIR = ROOT_DIR / "data" / "raw"              # CSV bruts et sales (entrée de la pipeline)
INTERIM_DIR = ROOT_DIR / "data" / "interim"      # fichiers intermédiaires (utilisés par Airflow)
PROCESSED_DIR = ROOT_DIR / "data" / "processed"  # CSV propres
POWERBI_DIR = PROCESSED_DIR / "powerbi"          # exports pour Power BI
REPORTS_DIR = ROOT_DIR / "reports"               # rapport qualité + graphiques
SQL_DIR = ROOT_DIR / "sql"

SOURCE_FILE = SOURCE_DIR / "healthcare_dataset.csv"
RAW_FILES = ["patients", "admissions", "departments", "staff"]

# --- Base de données ---
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "hospital_dw")
DB_USER = os.getenv("DB_USER", "hospital")
DB_PASSWORD = os.getenv("DB_PASSWORD", "hospital")
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}",
)

# --- Qualité des données ---
MAX_MISSING_RATE = float(os.getenv("MAX_MISSING_RATE", "0.05"))  # 5 % max après nettoyage
MAX_WAITING_TIME = 24 * 60  # au-delà de 24 h d'attente, la valeur est jugée impossible

# --- Agent IA (optionnel) ---
# LLM_PROVIDER : "ollama" (gratuit, local), "anthropic" (Claude, clé payante),
#                "openai" (toute API compatible OpenAI, ex : Groq) ou vide (mode sans LLM)
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "").strip().lower()
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://localhost:11434/v1")  # adresse d'Ollama
if not LLM_PROVIDER and ANTHROPIC_API_KEY:
    LLM_PROVIDER = "anthropic"  # compatibilité : une clé Claude seule suffit
DEFAULT_MODELS = {"anthropic": "claude-sonnet-4-6", "ollama": "qwen2.5-coder:7b", "openai": ""}
LLM_MODEL = os.getenv("LLM_MODEL") or DEFAULT_MODELS.get(LLM_PROVIDER, "")

# --- Logging ---
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")


def get_logger(name: str) -> logging.Logger:
    """Retourne un logger formaté de façon identique dans tout le projet."""
    logging.basicConfig(
        level=LOG_LEVEL,
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )
    logging.getLogger("matplotlib").setLevel(logging.WARNING)  # logs matplotlib trop bavards
    return logging.getLogger(name)


def get_engine():
    """Crée la connexion SQLAlchemy vers PostgreSQL."""
    from sqlalchemy import create_engine

    return create_engine(DATABASE_URL, pool_pre_ping=True)
