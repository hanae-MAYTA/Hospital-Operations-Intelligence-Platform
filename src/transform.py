"""
Étape TRANSFORM : nettoie les données brutes et construit les tables du schéma en étoile.
Dates standardisées, noms de services unifiés, doublons supprimés, valeurs impossibles
corrigées, valeurs manquantes imputées, puis création des variables utiles (features).

Auteures : Hanae MAYTA et Wafae ZALOUK

Stratégie pour les valeurs manquantes / impossibles (documentée dans le README) :
- waiting_time, billing_amount : médiane DU SERVICE (les urgences attendent plus que la rhumato)
- admission_hour : heure la plus fréquente du service
- age : médiane globale ; discharge_date : date d'entrée + durée de séjour médiane du service
- staff_id absent ou inconnu : "S000" (membre du personnel "Non renseigné")
- date d'entrée illisible ou service inconnu : ligne supprimée (impossible à rattacher)
"""
import numpy as np
import pandas as pd

from src.config import MAX_WAITING_TIME, get_logger

log = get_logger("transform")

DATE_FORMATS = ["%Y-%m-%d", "%d/%m/%Y", "%d-%b-%Y"]  # ISO, français, texte (ex : 31-Jan-2024)

# Dictionnaire de correspondance : toutes les variantes rencontrées -> nom officiel
DEPARTMENT_MAPPING = {
    "emergency": "Emergency", "urgence": "Emergency", "urgences": "Emergency", "er": "Emergency",
    "cardiology": "Cardiology", "cardiologie": "Cardiology", "cardio": "Cardiology",
    "oncology": "Oncology", "oncologie": "Oncology",
    "endocrinology": "Endocrinology", "endocrinologie": "Endocrinology", "endocrino": "Endocrinology",
    "pulmonology": "Pulmonology", "pneumologie": "Pulmonology",
    "rheumatology": "Rheumatology", "rhumatologie": "Rheumatology",
}
UNKNOWN_STAFF = "S000"
DAY_NAMES = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
MONTH_NAMES = ["Janvier", "Février", "Mars", "Avril", "Mai", "Juin", "Juillet",
               "Août", "Septembre", "Octobre", "Novembre", "Décembre"]


# ---------- Fonctions de nettoyage réutilisables (testées dans tests/) ----------

def parse_dates(series: pd.Series) -> pd.Series:
    """Convertit des dates écrites dans plusieurs formats. Les dates illisibles deviennent NaT."""
    result = pd.Series(pd.NaT, index=series.index, dtype="datetime64[ns]")
    text = series.astype("string").str.strip()
    for fmt in DATE_FORMATS:
        parsed = pd.to_datetime(text, format=fmt, errors="coerce")
        result = result.fillna(parsed)
    return result


def standardize_department(series: pd.Series) -> pd.Series:
    """Unifie les noms de services (Urgence / ER / Emergency -> Emergency). Inconnu -> NaN."""
    return series.astype("string").str.strip().str.lower().map(DEPARTMENT_MAPPING)


def to_number(series: pd.Series) -> pd.Series:
    """Convertit en nombre ; tout ce qui n'est pas un nombre devient NaN."""
    return pd.to_numeric(series, errors="coerce")


def replace_impossible(series: pd.Series, low: float, high: float) -> tuple[pd.Series, int]:
    """Remplace par NaN les valeurs hors de l'intervalle [low, high]. Retourne aussi le nombre."""
    mask = (series < low) | (series > high)
    return series.mask(mask), int(mask.sum())


def fill_with_group_median(df: pd.DataFrame, column: str, group: str) -> int:
    """Remplit les NaN d'une colonne par la médiane de son groupe (ex : par service)."""
    missing = int(df[column].isna().sum())
    df[column] = df[column].fillna(df.groupby(group)[column].transform("median"))
    return missing


# ---------- Nettoyage table par table ----------

def clean_patients(raw: pd.DataFrame) -> pd.DataFrame:
    """Patients : doublons supprimés, noms en casse propre, valeurs manquantes -> 'Unknown'."""
    df = raw.drop_duplicates("patient_id").copy()
    df["full_name"] = df["full_name"].str.strip().str.title()      # "LesLie TErRy" -> "Leslie Terry"
    df["gender"] = df["gender"].fillna("Unknown")
    df["insurance_provider"] = df["insurance_provider"].fillna("Unknown")
    df["birth_year"] = to_number(df["birth_year"]).astype("Int64")
    log.info("patients   : %d -> %d lignes (doublons supprimés : %d)",
             len(raw), len(df), len(raw) - len(df))
    return df.reset_index(drop=True)


def clean_departments(raw: pd.DataFrame) -> pd.DataFrame:
    """Services : types numériques et noms officiels."""
    df = raw.drop_duplicates("department_id").copy()
    for col in ["department_id", "capacity_beds", "daily_capacity"]:
        df[col] = to_number(df[col]).astype(int)
    df["department_name"] = standardize_department(df["department_name"])
    return df.reset_index(drop=True)


def clean_staff(raw: pd.DataFrame) -> pd.DataFrame:
    """Personnel : doublons supprimés, rôle manquant -> 'Unknown', ajout du membre 'Non renseigné'."""
    df = raw.drop_duplicates("staff_id").copy()
    df["role"] = df["role"].fillna("Unknown")
    df["department_id"] = to_number(df["department_id"]).astype("Int64")
    placeholder = pd.DataFrame([{"staff_id": UNKNOWN_STAFF, "staff_name": "Non renseigné",
                                 "role": "Unknown", "department_id": pd.NA}]).astype({"department_id": "Int64"})
    df = pd.concat([df, placeholder], ignore_index=True)
    df["department_id"] = df["department_id"].astype("Int64")
    log.info("staff      : %d -> %d lignes (+1 ligne 'Non renseigné')", len(raw), len(df))
    return df


def clean_admissions(raw: pd.DataFrame, patients: pd.DataFrame, staff: pd.DataFrame,
                     stats: dict) -> pd.DataFrame:
    """Admissions : le cœur du nettoyage. Remplit `stats` avec ce qui a été corrigé."""
    df = raw.copy()
    stats["rows_before"] = len(df)

    # 1) Doublons exacts (même admission exportée deux fois)
    df = df.drop_duplicates("admission_id")
    stats["duplicates_admission_id"] = stats["rows_before"] - len(df)

    # 2) Types : dates, services, nombres
    df["admission_date"] = parse_dates(df["admission_date"])
    df["discharge_date"] = parse_dates(df["discharge_date"])
    df["department"] = standardize_department(df["department"])
    for col in ["admission_hour", "age", "staff_on_duty", "waiting_time",
                "billing_amount", "room_number"]:
        df[col] = to_number(df[col])

    # 3) Lignes inutilisables : date d'entrée illisible ou service inconnu
    unusable = df["admission_date"].isna() | df["department"].isna()
    stats["dropped_unusable"] = int(unusable.sum())
    df = df[~unusable]

    # 4) Doublons "métier" : même patient, mêmes dates, même chambre, même pathologie
    before = len(df)
    df = df.drop_duplicates(["patient_id", "admission_date", "discharge_date",
                             "medical_condition", "room_number"])
    stats["duplicates_business"] = before - len(df)

    # 5) Patients inconnus (clé étrangère cassée) : ligne supprimée
    orphan = ~df["patient_id"].isin(patients["patient_id"])
    stats["dropped_unknown_patient"] = int(orphan.sum())
    df = df[~orphan].copy()

    # 6) Sortie avant l'entrée : erreur de saisie, on inverse les deux dates
    inverted = df["discharge_date"] < df["admission_date"]
    df.loc[inverted, ["admission_date", "discharge_date"]] = (
        df.loc[inverted, ["discharge_date", "admission_date"]].to_numpy()
    )
    stats["dates_inverted_fixed"] = int(inverted.sum())

    # 7) Valeurs impossibles -> NaN (puis imputées plus bas)
    df["waiting_time"], stats["waiting_time_impossible"] = replace_impossible(
        df["waiting_time"], 0, MAX_WAITING_TIME)
    df["billing_amount"], stats["billing_negative"] = replace_impossible(
        df["billing_amount"], 0, np.inf)
    df["age"], stats["age_impossible"] = replace_impossible(df["age"], 0, 110)

    # 8) Personnel absent ou inconnu -> "S000"
    unknown_staff = df["staff_id"].isna() | ~df["staff_id"].isin(staff["staff_id"])
    stats["staff_unknown"] = int(unknown_staff.sum())
    df.loc[unknown_staff, "staff_id"] = UNKNOWN_STAFF

    # 9) Imputation des valeurs manquantes (stratégie en haut du fichier)
    stats["waiting_time_imputed"] = fill_with_group_median(df, "waiting_time", "department")
    stats["billing_imputed"] = fill_with_group_median(df, "billing_amount", "department")
    stats["age_imputed"] = int(df["age"].isna().sum())
    df["age"] = df["age"].fillna(df["age"].median())
    stats["hour_imputed"] = int(df["admission_hour"].isna().sum())
    mode_hour = df.groupby("department")["admission_hour"].transform(lambda s: s.mode().iloc[0])
    df["admission_hour"] = df["admission_hour"].fillna(mode_hour)
    stats["discharge_imputed"] = int(df["discharge_date"].isna().sum())
    los = (df["discharge_date"] - df["admission_date"]).dt.days
    median_los = los.groupby(df["department"]).transform("median")
    df["discharge_date"] = df["discharge_date"].fillna(
        df["admission_date"] + pd.to_timedelta(median_los, unit="D"))

    stats["rows_after"] = len(df)
    return df


def add_features(df: pd.DataFrame, departments: pd.DataFrame) -> pd.DataFrame:
    """Feature engineering : durée de séjour, calendrier, âge, charge par membre du personnel."""
    df = df.copy()
    df["length_of_stay"] = (df["discharge_date"] - df["admission_date"]).dt.days
    df["day_of_week"] = df["admission_date"].dt.dayofweek          # 0 = lundi
    df["hour"] = df["admission_hour"].astype(int)
    df["month"] = df["admission_date"].dt.month
    df["patient_age"] = df["age"].round().astype(int)
    # Charge : nombre d'admissions du service ce jour-là / personnel présent
    daily_count = df.groupby(["admission_date", "department"])["admission_id"].transform("size")
    df["patients_per_staff"] = (daily_count / df["staff_on_duty"].clip(lower=1)).round(2)
    df["date_id"] = df["admission_date"].dt.strftime("%Y%m%d").astype(int)
    name_to_id = dict(zip(departments["department_name"], departments["department_id"]))
    df["department_id"] = df["department"].map(name_to_id)
    return df


def build_dim_date(dates: pd.Series) -> pd.DataFrame:
    """Dimension calendrier : une ligne par jour entre la première et la dernière admission."""
    days = pd.date_range(dates.min(), dates.max(), freq="D")
    return pd.DataFrame({
        "date_id": days.strftime("%Y%m%d").astype(int),
        "full_date": days.date,
        "year": days.year, "quarter": days.quarter, "month": days.month,
        "month_name": [MONTH_NAMES[m - 1] for m in days.month],
        "day": days.day, "day_of_week": days.dayofweek,
        "day_name": [DAY_NAMES[d] for d in days.dayofweek],
        "is_weekend": days.dayofweek >= 5,
    })


FACT_COLUMNS = [
    "admission_id", "patient_id", "date_id", "department_id", "staff_id",
    "admission_date", "discharge_date", "hour", "day_of_week", "month",
    "admission_type", "medical_condition", "patient_age", "waiting_time",
    "length_of_stay", "cost", "staff_on_duty", "patients_per_staff",
    "room_number", "medication", "test_result",
]


def build_fact(df: pd.DataFrame) -> pd.DataFrame:
    """Table de faits : une ligne par admission, avec les clés vers les dimensions."""
    fact = df.rename(columns={"billing_amount": "cost", "test_results": "test_result"})
    fact["waiting_time"] = fact["waiting_time"].round().astype(int)
    fact["cost"] = fact["cost"].round(2)
    fact["room_number"] = fact["room_number"].astype("Int64")
    fact["staff_on_duty"] = fact["staff_on_duty"].astype(int)
    fact["admission_date"] = fact["admission_date"].dt.date
    fact["discharge_date"] = fact["discharge_date"].dt.date
    return fact[FACT_COLUMNS].sort_values("admission_id").reset_index(drop=True)


def log_summary(stats: dict) -> None:
    """Affiche le résumé AVANT / APRÈS du nettoyage des admissions."""
    log.info("admissions : %d -> %d lignes", stats["rows_before"], stats["rows_after"])
    for key, value in stats.items():
        if key not in ("rows_before", "rows_after") and value:
            log.info("   - %-26s : %d", key, value)


def transform(raw: dict[str, pd.DataFrame]) -> tuple[dict[str, pd.DataFrame], dict]:
    """Nettoie les 4 tables brutes et retourne (tables du schéma en étoile, statistiques)."""
    log.info("TRANSFORM - nettoyage et construction du schéma en étoile")
    stats: dict = {}
    patients = clean_patients(raw["patients"])
    departments = clean_departments(raw["departments"])
    staff = clean_staff(raw["staff"])
    admissions = clean_admissions(raw["admissions"], patients, staff, stats)
    admissions = add_features(admissions, departments)
    log_summary(stats)

    tables = {
        "dim_patient": patients,
        "dim_department": departments,
        "dim_staff": staff,
        "dim_date": build_dim_date(admissions["admission_date"]),
        "fact_admission": build_fact(admissions),
    }
    return tables, stats
