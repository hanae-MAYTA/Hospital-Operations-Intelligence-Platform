"""
Test de bout en bout sur un petit jeu de données : CSV -> Extract -> Transform -> Validate -> Load.
Le chargement se fait dans un schéma PostgreSQL temporaire (supprimé à la fin) ;
si PostgreSQL n'est pas joignable, cette partie est ignorée (skip).
Auteures : Hanae MAYTA et Wafae ZALOUK
"""
import pytest
from sqlalchemy import create_engine, text

from src.config import DATABASE_URL
from src.extract import ExtractError, extract
from src.load import load
from src.pipeline import quality_check
from src.transform import transform
from src.validate import validate

TEST_SCHEMA = "test_e2e"


def write_raw_csv(raw_data, folder):
    for name, df in raw_data.items():
        df.to_csv(folder / f"{name}.csv", index=False)


def test_extract_missing_file_raises(tmp_path):
    with pytest.raises(ExtractError, match="introuvable"):
        extract(tmp_path)


def test_extract_transform_validate(raw_data, tmp_path):
    write_raw_csv(raw_data, tmp_path)
    raw = extract(tmp_path)
    assert len(raw["admissions"]) == 6
    tables, stats = transform(raw)
    assert stats["duplicates_admission_id"] == 1
    results = validate(tables, stats, report_path=tmp_path / "report.md")
    assert all(r["passed"] for r in results if r["critical"])


@pytest.fixture
def test_engine():
    """Moteur PostgreSQL pointant sur un schéma de test isolé."""
    try:
        admin = create_engine(DATABASE_URL)
        with admin.begin() as conn:
            conn.execute(text(f"DROP SCHEMA IF EXISTS {TEST_SCHEMA} CASCADE"))
            conn.execute(text(f"CREATE SCHEMA {TEST_SCHEMA}"))
    except Exception as exc:
        pytest.skip(f"PostgreSQL indisponible : {exc}")
    engine = create_engine(DATABASE_URL, connect_args={"options": f"-csearch_path={TEST_SCHEMA}"})
    yield engine
    engine.dispose()
    with admin.begin() as conn:
        conn.execute(text(f"DROP SCHEMA IF EXISTS {TEST_SCHEMA} CASCADE"))


def test_load_is_idempotent(raw_data, tmp_path, test_engine):
    write_raw_csv(raw_data, tmp_path)
    tables, stats = transform(extract(tmp_path))
    validate(tables, stats, report_path=tmp_path / "report.md")
    load(tables, engine=test_engine)
    load(tables, engine=test_engine)          # 2e chargement : ne doit rien dupliquer
    quality_check(tables, engine=test_engine)
    with test_engine.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM fact_admission")).scalar() == 5
