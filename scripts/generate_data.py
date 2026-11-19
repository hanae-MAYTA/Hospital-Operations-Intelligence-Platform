"""
Prépare les données SOURCES de la pipeline à partir du dataset Kaggle "healthcare_dataset.csv".
Le dataset réel est enrichi (service, heure, temps d'attente, personnel) puis volontairement
"sali" (3 formats de dates, noms de services variés, doublons, valeurs manquantes ou impossibles).

Auteures : Hanae MAYTA et Wafae ZALOUK
Usage : python scripts/generate_data.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.config import RAW_DIR, SOURCE_FILE, get_logger  # noqa: E402

log = get_logger("generate_data")
rng = np.random.default_rng(42)  # seed fixe => mêmes données à chaque exécution

# --- Référentiel des services : pathologie -> service, capacités ---
CONDITION_TO_DEPT = {
    "Cancer": "Oncology", "Diabetes": "Endocrinology", "Obesity": "Endocrinology",
    "Asthma": "Pulmonology", "Hypertension": "Cardiology", "Arthritis": "Rheumatology",
}
DEPARTMENTS = pd.DataFrame({
    "department_id": [1, 2, 3, 4, 5, 6],
    "department_name": ["Emergency", "Cardiology", "Oncology",
                        "Endocrinology", "Pulmonology", "Rheumatology"],
    "capacity_beds": [170, 60, 60, 115, 60, 60],
    "daily_capacity": [14, 5, 5, 9, 5, 5],      # admissions/jour que le service peut absorber
    "base_staff": [8, 4, 4, 4, 3, 3],           # personnel présent un jour normal
})
# Variantes "sales" des noms de services, comme dans de vrais exports hospitaliers
DEPT_VARIANTS = {
    "Emergency": ["Emergency", "Urgence", "Urgences", "ER", " emergency"],
    "Cardiology": ["Cardiology", "Cardiologie", "CARDIO"],
    "Oncology": ["Oncology", "Oncologie"],
    "Endocrinology": ["Endocrinology", "Endocrinologie", "Endocrino"],
    "Pulmonology": ["Pulmonology", "Pneumologie"],
    "Rheumatology": ["Rheumatology", "Rhumatologie"],
}


def assign_department(df: pd.DataFrame) -> pd.Series:
    """Urgences si admission de type Emergency, sinon service lié à la pathologie."""
    dept = df["Medical Condition"].map(CONDITION_TO_DEPT)
    return dept.where(df["Admission Type"] != "Emergency", "Emergency")


def add_peaks(df: pd.DataFrame, last_date: pd.Timestamp) -> pd.DataFrame:
    """Injecte des pics anormaux d'admissions aux urgences (dont le dernier jour = 'hier')."""
    all_dates = df["adm_date"].drop_duplicates().sort_values()
    peak_dates = list(rng.choice(all_dates.iloc[:-1], size=8, replace=False)) + [last_date]
    extra = []
    for d in peak_dates:
        sample = df.sample(n=int(rng.integers(30, 45)), random_state=int(rng.integers(1e6))).copy()
        los = sample["dis_date"] - sample["adm_date"]
        sample["adm_date"] = pd.Timestamp(d)
        sample["dis_date"] = sample["adm_date"] + los
        sample["Admission Type"] = "Emergency"
        sample["department"] = "Emergency"
        extra.append(sample)
    log.info("Pics injectés sur %d jours (dont le dernier jour %s)", len(peak_dates), last_date.date())
    return pd.concat([df] + extra, ignore_index=True)


def build_staffing(dates: pd.Series, last_date: pd.Timestamp) -> pd.DataFrame:
    """Personnel présent par jour et par service, avec des jours de sous-effectif."""
    grid = pd.MultiIndex.from_product(
        [dates.drop_duplicates(), DEPARTMENTS["department_name"]], names=["adm_date", "department"]
    ).to_frame(index=False)
    grid = grid.merge(DEPARTMENTS[["department_name", "base_staff"]],
                      left_on="department", right_on="department_name")
    variation = rng.integers(-1, 2, size=len(grid))
    shortage = rng.random(len(grid)) < 0.06            # 6 % de jours en sous-effectif
    staff = grid["base_staff"] + variation
    staff = np.where(shortage, np.ceil(grid["base_staff"] * 0.5), staff)
    grid["staff_on_duty"] = np.maximum(staff, 1).astype(int)
    # Scénario de démo : la veille ("hier"), les urgences tournent à moitié d'effectif
    grid.loc[(grid["adm_date"] == last_date) & (grid["department"] == "Emergency"), "staff_on_duty"] = 4
    return grid[["adm_date", "department", "staff_on_duty"]]


def sample_hours(departments: pd.Series) -> np.ndarray:
    """Heures d'arrivée : pics à 11 h et 19 h aux urgences, heures ouvrées ailleurs."""
    er_weights = np.array([1, 1, 1, 1, 1, 1, 2, 3, 4, 5, 7, 9, 8, 6, 5, 5, 6, 8, 9, 10, 8, 5, 3, 2], float)
    day_weights = np.array([0] * 7 + [4, 8, 9, 9, 7, 5, 6, 7, 6, 4, 2] + [0] * 6, float)
    is_er = (departments == "Emergency").to_numpy()
    hours = np.where(
        is_er,
        rng.choice(24, size=len(departments), p=er_weights / er_weights.sum()),
        rng.choice(24, size=len(departments), p=day_weights / day_weights.sum()),
    )
    return hours


def compute_waiting_time(df: pd.DataFrame) -> np.ndarray:
    """Temps d'attente (min) qui augmente avec le nombre de patients par membre du personnel."""
    daily = df.groupby(["adm_date", "department"])["Name"].transform("size")
    ratio = daily / df["staff_on_duty"]
    is_er = df["department"] == "Emergency"
    base = np.where(is_er, 15, 10)
    slope = np.where(is_er, 18, 8)
    rush_hour = np.where(is_er & df["hour"].isin([10, 11, 12, 18, 19, 20]), 12, 0)
    noise = rng.normal(0, 6, len(df))
    return np.clip(base + slope * ratio + rush_hour + noise, 1, None).round().astype(int)


def format_dates(dates: pd.Series) -> pd.Series:
    """Écrit les dates dans 3 formats différents (ISO, français, texte)."""
    choice = rng.choice(3, size=len(dates), p=[0.6, 0.25, 0.15])
    iso = dates.dt.strftime("%Y-%m-%d")
    fr = dates.dt.strftime("%d/%m/%Y")
    txt = dates.dt.strftime("%d-%b-%Y")
    return pd.Series(np.select([choice == 0, choice == 1], [iso, fr], txt), index=dates.index)


def make_dirty(series: pd.Series, rate: float, value=np.nan) -> pd.Series:
    """Remplace une fraction `rate` des valeurs par `value` (valeur manquante ou impossible)."""
    s = series.astype(object).copy()
    mask = rng.random(len(s)) < rate
    s[mask] = value
    return s


def build_staff_table(source: pd.DataFrame) -> pd.DataFrame:
    """Crée le référentiel du personnel (médecins et infirmiers) par service."""
    names = source["Doctor"].drop_duplicates().sample(200, random_state=42).tolist()
    rows, i = [], 1
    for _, dept in DEPARTMENTS.iterrows():
        for _ in range(dept["base_staff"] * 3):
            role = "Doctor" if i % 3 == 1 else "Nurse"
            rows.append({"staff_id": f"S{i:03d}", "staff_name": names[i], "role": role,
                         "department_id": dept["department_id"]})
            i += 1
    staff = pd.DataFrame(rows)
    staff.loc[[3, 17], "role"] = np.nan                      # rôles manquants
    return pd.concat([staff, staff.iloc[[5]]], ignore_index=True)  # 1 doublon


def main() -> None:
    log.info("Lecture du dataset source : %s", SOURCE_FILE)
    src = pd.read_csv(SOURCE_FILE)
    src["adm_date"] = pd.to_datetime(src["Date of Admission"])
    src["dis_date"] = pd.to_datetime(src["Discharge Date"])
    src["department"] = assign_department(src)
    last_date = src["adm_date"].max()

    df = add_peaks(src, last_date)
    df = df.merge(build_staffing(df["adm_date"], last_date), on=["adm_date", "department"])
    df = df.sort_values(["adm_date", "department"]).reset_index(drop=True)
    df["hour"] = sample_hours(df["department"])
    df["waiting_time"] = compute_waiting_time(df)

    # --- Patients : un patient = même nom (sans tenir compte de la casse) + sexe + groupe sanguin ---
    df["patient_key"] = df["Name"].str.lower().str.strip() + "|" + df["Gender"] + "|" + df["Blood Type"]
    keys = df["patient_key"].drop_duplicates().reset_index(drop=True)
    key_to_id = {k: f"P{i + 1:06d}" for i, k in enumerate(keys)}
    df["patient_id"] = df["patient_key"].map(key_to_id)

    first = df.drop_duplicates("patient_id")
    patients = pd.DataFrame({
        "patient_id": first["patient_id"],
        "full_name": first["Name"],                       # casse sale gardée (ex : "LesLie TErRy")
        "gender": make_dirty(first["Gender"], 0.01),
        "blood_type": first["Blood Type"],
        "birth_year": first["adm_date"].dt.year - first["Age"],
        "insurance_provider": make_dirty(first["Insurance Provider"], 0.02),
    })
    patients = pd.concat([patients, patients.sample(frac=0.02, random_state=1)], ignore_index=True)

    # --- Personnel : un membre du service est associé à chaque admission ---
    staff = build_staff_table(src)
    staff_by_dept = staff.drop_duplicates("staff_id").merge(DEPARTMENTS, on="department_id")
    staff_lists = staff_by_dept.groupby("department_name")["staff_id"].apply(list).to_dict()
    df["staff_id"] = [rng.choice(staff_lists[d]) for d in df["department"]]

    # --- Admissions sales ---
    admissions = pd.DataFrame({
        "admission_id": [f"A{i + 1:06d}" for i in range(len(df))],
        "patient_id": df["patient_id"],
        "department": [rng.choice(DEPT_VARIANTS[d]) for d in df["department"]],
        "admission_date": format_dates(df["adm_date"]),
        "admission_hour": make_dirty(df["hour"], 0.01),
        "discharge_date": make_dirty(format_dates(df["dis_date"]), 0.005),
        "admission_type": df["Admission Type"],
        "medical_condition": df["Medical Condition"],
        "age": df["Age"],
        "staff_id": make_dirty(make_dirty(df["staff_id"], 0.01), 0.003, "S999"),
        "staff_on_duty": df["staff_on_duty"],
        "waiting_time": df["waiting_time"],
        "billing_amount": make_dirty(df["Billing Amount"].round(2), 0.02),
        "room_number": df["Room Number"],
        "medication": df["Medication"],
        "test_results": df["Test Results"],
    })
    # Valeurs impossibles
    admissions["waiting_time"] = make_dirty(admissions["waiting_time"], 0.03)  # manquants
    neg = rng.random(len(admissions)) < 0.01
    admissions.loc[neg, "waiting_time"] = -admissions.loc[neg, "waiting_time"].abs()
    admissions["waiting_time"] = make_dirty(admissions["waiting_time"], 0.002, 99999)
    admissions["age"] = make_dirty(admissions["age"], 0.003, 150)
    swap = rng.random(len(admissions)) < 0.002               # sortie AVANT l'entrée
    admissions.loc[swap, ["admission_date", "discharge_date"]] = (
        admissions.loc[swap, ["discharge_date", "admission_date"]].to_numpy()
    )
    # Doublons exacts (même admission exportée deux fois)
    admissions = pd.concat([admissions, admissions.sample(frac=0.01, random_state=2)])
    admissions = admissions.sample(frac=1, random_state=3).reset_index(drop=True)  # ordre mélangé

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    outputs = {
        "patients": patients,
        "admissions": admissions,
        "departments": DEPARTMENTS.drop(columns="base_staff"),
        "staff": staff,
    }
    for name, table in outputs.items():
        table.to_csv(RAW_DIR / f"{name}.csv", index=False)
        log.info("%-12s -> %6d lignes écrites dans data/raw/%s.csv", name, len(table), name)


if __name__ == "__main__":
    main()
