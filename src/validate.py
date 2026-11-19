"""
Étape VALIDATE : contrôles qualité automatiques sur les données nettoyées, AVANT le chargement.
Chaque contrôle donne ✅ ou ❌ dans reports/data_quality_report.md. Si un contrôle CRITIQUE
échoue, la pipeline s'arrête (ValidationError) : on ne charge jamais de données fausses.

Auteures : Hanae MAYTA et Wafae ZALOUK
"""
from datetime import datetime
from pathlib import Path

import pandas as pd

from src.config import MAX_MISSING_RATE, MAX_WAITING_TIME, REPORTS_DIR, get_logger

log = get_logger("validate")

REQUIRED_COLUMNS = {
    "dim_patient": ["patient_id", "full_name", "gender", "blood_type"],
    "dim_department": ["department_id", "department_name", "daily_capacity"],
    "dim_staff": ["staff_id", "staff_name", "role"],
    "dim_date": ["date_id", "full_date"],
    "fact_admission": ["admission_id", "patient_id", "date_id", "department_id", "staff_id",
                       "waiting_time", "length_of_stay", "cost"],
}
PRIMARY_KEYS = {"dim_patient": "patient_id", "dim_department": "department_id",
                "dim_staff": "staff_id", "dim_date": "date_id", "fact_admission": "admission_id"}
FOREIGN_KEYS = [("patient_id", "dim_patient"), ("date_id", "dim_date"),
                ("department_id", "dim_department"), ("staff_id", "dim_staff")]


class ValidationError(Exception):
    """Erreur levée quand au moins un contrôle critique échoue."""


def check(name: str, passed: bool, details: str, critical: bool = True) -> dict:
    """Crée le résultat d'un contrôle."""
    return {"name": name, "passed": bool(passed), "details": details, "critical": critical}


def check_required_columns(tables: dict) -> list[dict]:
    """Toutes les colonnes obligatoires sont présentes."""
    results = []
    for table, columns in REQUIRED_COLUMNS.items():
        missing = [c for c in columns if c not in tables[table].columns]
        results.append(check(f"Colonnes obligatoires ({table})", not missing,
                             f"manquantes : {missing}" if missing else "toutes présentes"))
    return results


def check_not_empty(tables: dict) -> list[dict]:
    """Aucune table n'est vide."""
    return [check(f"Table non vide ({t})", len(df) > 0, f"{len(df)} lignes") for t, df in tables.items()]


def check_no_duplicates(tables: dict) -> list[dict]:
    """La clé primaire de chaque table est unique."""
    results = []
    for table, pk in PRIMARY_KEYS.items():
        if pk not in tables[table].columns:
            continue
        dup = int(tables[table][pk].duplicated().sum())
        results.append(check(f"Pas de doublons ({table}.{pk})", dup == 0, f"{dup} doublon(s)"))
    return results


def check_missing_rate(fact: pd.DataFrame) -> dict:
    """Taux de valeurs manquantes sous le seuil, pour chaque colonne obligatoire."""
    cols = [c for c in REQUIRED_COLUMNS["fact_admission"] if c in fact.columns]
    worst = fact[cols].isna().mean().max() if cols else 0.0
    return check("Taux de valeurs manquantes", worst <= MAX_MISSING_RATE,
                 f"pire colonne : {worst:.2%} (seuil {MAX_MISSING_RATE:.0%})")


def check_waiting_time(fact: pd.DataFrame) -> list[dict]:
    """Temps d'attente : jamais négatif (critique), jamais au-delà de 24 h (avertissement)."""
    negative = int((fact["waiting_time"] < 0).sum())
    too_long = int((fact["waiting_time"] > MAX_WAITING_TIME).sum())
    return [
        check("Pas de waiting_time négatif", negative == 0, f"{negative} valeur(s) négative(s)"),
        check("waiting_time < 24 h", too_long == 0, f"{too_long} valeur(s) > 24 h", critical=False),
    ]


def check_dates(fact: pd.DataFrame) -> list[dict]:
    """Dates présentes, sortie après l'entrée, dates plausibles."""
    adm = pd.to_datetime(fact["admission_date"], errors="coerce")
    dis = pd.to_datetime(fact["discharge_date"], errors="coerce")
    invalid = int(adm.isna().sum() + dis.isna().sum())
    inverted = int((dis < adm).sum())
    future = int((adm > pd.Timestamp(datetime.now())).sum())
    return [
        check("Dates valides", invalid == 0, f"{invalid} date(s) illisible(s)"),
        check("Sortie après l'entrée", inverted == 0, f"{inverted} séjour(s) inversé(s)"),
        check("Pas de date dans le futur", future == 0, f"{future} date(s) future(s)", critical=False),
    ]


def check_foreign_keys(tables: dict) -> list[dict]:
    """Chaque clé étrangère de fact_admission existe dans sa dimension."""
    fact = tables["fact_admission"]
    results = []
    for column, dim in FOREIGN_KEYS:
        orphans = int((~fact[column].isin(tables[dim][PRIMARY_KEYS[dim]])).sum())
        results.append(check(f"Clé étrangère {column} -> {dim}", orphans == 0, f"{orphans} orpheline(s)"))
    return results


def check_business_rules(fact: pd.DataFrame) -> list[dict]:
    """Règles métier non bloquantes : coût positif, âge plausible, durée de séjour positive."""
    return [
        check("Coût positif", (fact["cost"] >= 0).all(), f"{int((fact['cost'] < 0).sum())} négatif(s)", False),
        check("Âge entre 0 et 110", fact["patient_age"].between(0, 110).all(), "âges plausibles", False),
        check("Durée de séjour >= 0", (fact["length_of_stay"] >= 0).all(), "durées positives", False),
    ]


def run_checks(tables: dict) -> list[dict]:
    """Lance tous les contrôles et retourne la liste des résultats."""
    results = check_required_columns(tables)
    if not all(r["passed"] for r in results):
        return results  # inutile d'aller plus loin si des colonnes manquent
    fact = tables["fact_admission"]
    results += check_not_empty(tables)
    results += check_no_duplicates(tables)
    results.append(check_missing_rate(fact))
    results += check_waiting_time(fact)
    results += check_dates(fact)
    results += check_foreign_keys(tables)
    results += check_business_rules(fact)
    return results


def write_report(results: list[dict], stats: dict, tables: dict, path: Path) -> None:
    """Écrit le rapport qualité en Markdown (✅ / ❌)."""
    ok = sum(r["passed"] for r in results)
    lines = [
        "# Rapport de qualité des données",
        "",
        f"*Généré le {datetime.now():%d/%m/%Y à %H:%M} — Hanae MAYTA & Wafae ZALOUK*",
        "",
        f"**Résultat : {ok}/{len(results)} contrôles réussis**",
        "",
        "## Contrôles",
        "",
        "| Statut | Contrôle | Critique | Détail |",
        "|---|---|---|---|",
    ]
    for r in results:
        icon = "✅" if r["passed"] else "❌"
        lines.append(f"| {icon} | {r['name']} | {'oui' if r['critical'] else 'non'} | {r['details']} |")
    if stats:
        lines += ["", "## Nettoyage effectué (étape Transform)", "", "| Opération | Nombre |", "|---|---|"]
        lines += [f"| {k} | {v} |" for k, v in stats.items()]
    lines += ["", "## Volumes chargés", "", "| Table | Lignes |", "|---|---|"]
    lines += [f"| {t} | {len(df)} |" for t, df in tables.items()]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def validate(tables: dict, stats: dict | None = None,
             report_path: Path = REPORTS_DIR / "data_quality_report.md") -> list[dict]:
    """Valide les tables, écrit le rapport, et lève ValidationError si un contrôle critique échoue."""
    log.info("VALIDATE - contrôles qualité")
    results = run_checks(tables)
    for r in results:
        level = "info" if r["passed"] else ("error" if r["critical"] else "warning")
        getattr(log, level)("%s %s : %s", "✅" if r["passed"] else "❌", r["name"], r["details"])
    write_report(results, stats or {}, tables, report_path)
    log.info("Rapport qualité écrit : %s", report_path)

    failed = [r["name"] for r in results if r["critical"] and not r["passed"]]
    if failed:
        raise ValidationError(f"Contrôles critiques en échec : {failed}. Chargement annulé.")
    return results
