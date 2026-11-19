"""
Tests de l'étape TRANSFORM : dates, services, doublons, valeurs impossibles et features.
Auteures : Hanae MAYTA et Wafae ZALOUK
"""
import pandas as pd

from src.transform import parse_dates, replace_impossible, standardize_department


def test_parse_dates_three_formats():
    dates = parse_dates(pd.Series(["2024-01-31", "31/01/2024", "31-Jan-2024"]))
    assert (dates == pd.Timestamp("2024-01-31")).all()


def test_parse_dates_invalid_becomes_nat():
    dates = parse_dates(pd.Series(["pas une date", None, "2024-13-45"]))
    assert dates.isna().all()


def test_standardize_department_variants():
    result = standardize_department(pd.Series(["Urgence", "ER", " emergency", "Cardiologie", "CARDIO"]))
    assert result.tolist() == ["Emergency"] * 3 + ["Cardiology"] * 2


def test_standardize_department_unknown_is_nan():
    assert standardize_department(pd.Series(["Service inconnu"])).isna().all()


def test_replace_impossible_counts_values():
    series, count = replace_impossible(pd.Series([-5, 10, 99999]), 0, 1440)
    assert count == 2 and series.isna().sum() == 2


def test_duplicates_removed(clean_tables):
    fact = clean_tables["fact_admission"]
    assert fact["admission_id"].is_unique
    assert len(fact) == 5                                   # A4 en double -> 1 seule ligne
    assert clean_tables["dim_patient"]["patient_id"].is_unique


def test_no_negative_waiting_time(clean_tables):
    fact = clean_tables["fact_admission"]
    assert (fact["waiting_time"] >= 0).all()
    assert fact["waiting_time"].notna().all()


def test_impossible_values_fixed(clean_tables):
    fact = clean_tables["fact_admission"]
    assert fact["patient_age"].between(0, 110).all()        # âge 150 remplacé
    assert (fact["cost"] >= 0).all()                        # coût négatif remplacé


def test_inverted_dates_fixed(clean_tables):
    fact = clean_tables["fact_admission"].set_index("admission_id")
    assert str(fact.loc["A5", "admission_date"]) == "2024-01-18"
    assert (fact["length_of_stay"] >= 0).all()


def test_unknown_staff_mapped_to_placeholder(clean_tables):
    fact = clean_tables["fact_admission"].set_index("admission_id")
    assert fact.loc["A2", "staff_id"] == "S000"              # S999 inconnu
    assert fact.loc["A3", "staff_id"] == "S000"              # manquant


def test_features_created(clean_tables):
    fact = clean_tables["fact_admission"].set_index("admission_id")
    assert fact.loc["A1", "length_of_stay"] == 5
    assert fact.loc["A1", "day_of_week"] == 2               # 10/01/2024 = mercredi
    assert fact.loc["A1", "hour"] == 10
    for col in ["month", "patient_age", "patients_per_staff", "date_id"]:
        assert col in fact.columns


def test_patient_names_cleaned(clean_tables):
    names = clean_tables["dim_patient"].set_index("patient_id")["full_name"]
    assert names["P1"] == "Alice Martin"
