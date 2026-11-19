"""
Jeux de données de test : un petit hôpital "sale" de quelques lignes, construit à la main,
pour vérifier que Transform et Validate se comportent comme prévu.
Auteures : Hanae MAYTA et Wafae ZALOUK
"""
import pandas as pd
import pytest


@pytest.fixture
def raw_data() -> dict[str, pd.DataFrame]:
    """Données brutes avec les mêmes défauts que les vraies (lues en texte, comme Extract)."""
    patients = pd.DataFrame({
        "patient_id": ["P1", "P2", "P3", "P3"],                    # P3 en double
        "full_name": ["aLIce MARTIN", "Bob Durand", "chloé petit", "chloé petit"],
        "gender": ["Female", None, "Female", "Female"],            # sexe manquant
        "blood_type": ["A+", "O-", "B+", "B+"],
        "birth_year": ["1980", "1955", "2000", "2000"],
        "insurance_provider": ["Cigna", "Aetna", None, None],
    })
    departments = pd.DataFrame({
        "department_id": ["1", "2"], "department_name": ["Emergency", "Cardiology"],
        "capacity_beds": ["10", "5"], "daily_capacity": ["5", "3"],
    })
    staff = pd.DataFrame({
        "staff_id": ["S001", "S002"], "staff_name": ["Dr House", "Nurse Joy"],
        "role": ["Doctor", None], "department_id": ["1", "2"],
    })
    admissions = pd.DataFrame({
        "admission_id": ["A1", "A2", "A3", "A4", "A4", "A5"],      # A4 en double
        "patient_id": ["P1", "P2", "P3", "P1", "P1", "P2"],
        "department": ["Urgence", "ER", "Cardiologie", "CARDIO", "CARDIO", " emergency"],
        "admission_date": ["2024-01-10", "11/01/2024", "12-Jan-2024", "2024-01-12", "2024-01-12",
                           "2024-01-20"],                          # 3 formats + sortie inversée (A5)
        "admission_hour": ["10", "19", None, "9", "9", "11"],
        "discharge_date": ["2024-01-15", "2024-01-13", "20/01/2024", None, None, "2024-01-18"],
        "admission_type": ["Emergency", "Emergency", "Elective", "Urgent", "Urgent", "Emergency"],
        "medical_condition": ["Asthma", "Cancer", "Hypertension", "Hypertension", "Hypertension",
                              "Diabetes"],
        "age": ["44", "69", "150", "44", "44", "69"],               # âge impossible (150)
        "staff_id": ["S001", "S999", None, "S002", "S002", "S001"],  # inconnu + manquant
        "staff_on_duty": ["4", "4", "2", "2", "2", "5"],
        "waiting_time": ["30", "-15", "20", None, None, "45"],     # négatif + manquant
        "billing_amount": ["1000.5", "-20", "3000", "2500", "2500", None],
        "room_number": ["101", "102", "201", "202", "202", "103"],
        "medication": ["Aspirin"] * 6, "test_results": ["Normal"] * 6,
    })
    return {"patients": patients, "admissions": admissions,
            "departments": departments, "staff": staff}


@pytest.fixture
def clean_tables(raw_data):
    """Tables propres obtenues en passant les données de test dans Transform."""
    from src.transform import transform

    tables, _ = transform(raw_data)
    return tables
