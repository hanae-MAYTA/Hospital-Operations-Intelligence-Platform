"""
Tests de l'étape VALIDATE : les données propres passent, les données fausses sont BLOQUÉES.
Auteures : Hanae MAYTA et Wafae ZALOUK
"""
import pandas as pd
import pytest

from src.validate import ValidationError, validate


def test_clean_data_passes(clean_tables, tmp_path):
    results = validate(clean_tables, report_path=tmp_path / "report.md")
    assert all(r["passed"] for r in results if r["critical"])
    assert "✅" in (tmp_path / "report.md").read_text(encoding="utf-8")


def test_negative_waiting_time_fails(clean_tables, tmp_path):
    clean_tables["fact_admission"].loc[0, "waiting_time"] = -10
    with pytest.raises(ValidationError, match="waiting_time"):
        validate(clean_tables, report_path=tmp_path / "report.md")
    assert "❌" in (tmp_path / "report.md").read_text(encoding="utf-8")


def test_duplicates_fail(clean_tables, tmp_path):
    fact = clean_tables["fact_admission"]
    clean_tables["fact_admission"] = pd.concat([fact, fact.iloc[[0]]], ignore_index=True)
    with pytest.raises(ValidationError, match="doublons"):
        validate(clean_tables, report_path=tmp_path / "report.md")


def test_missing_column_fails(clean_tables, tmp_path):
    clean_tables["fact_admission"] = clean_tables["fact_admission"].drop(columns="cost")
    with pytest.raises(ValidationError, match="Colonnes obligatoires"):
        validate(clean_tables, report_path=tmp_path / "report.md")


def test_orphan_foreign_key_fails(clean_tables, tmp_path):
    clean_tables["fact_admission"].loc[0, "patient_id"] = "P_INCONNU"
    with pytest.raises(ValidationError, match="patient_id"):
        validate(clean_tables, report_path=tmp_path / "report.md")


def test_too_many_missing_values_fails(clean_tables, tmp_path):
    clean_tables["fact_admission"]["cost"] = None
    with pytest.raises(ValidationError, match="manquantes"):
        validate(clean_tables, report_path=tmp_path / "report.md")


def test_inverted_dates_fail(clean_tables, tmp_path):
    fact = clean_tables["fact_admission"]
    fact.loc[0, "discharge_date"] = pd.Timestamp("2000-01-01").date()
    with pytest.raises(ValidationError, match="Sortie"):
        validate(clean_tables, report_path=tmp_path / "report.md")
