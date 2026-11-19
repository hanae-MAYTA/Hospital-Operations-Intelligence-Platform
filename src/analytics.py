"""
Analytics : exporte les vues SQL en CSV pour Power BI (data/processed/powerbi/) et génère
des graphiques matplotlib d'aperçu dans reports/. Les données viennent du Data Warehouse.
Usage : python -m src.analytics

Auteures : Hanae MAYTA et Wafae ZALOUK
"""
import matplotlib

matplotlib.use("Agg")  # pas d'écran nécessaire
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from src.config import POWERBI_DIR, REPORTS_DIR, get_engine, get_logger  # noqa: E402

log = get_logger("analytics")

POWERBI_EXPORTS = ["vw_admissions_detail", "vw_daily_kpis", "vw_staff_load",
                   "vw_emergency_hourly", "vw_department_kpis", "vw_daily_occupancy"]
STAR_TABLES = ["fact_admission", "dim_patient", "dim_date", "dim_department", "dim_staff"]


def export_for_powerbi(engine) -> None:
    """Écrit chaque vue et chaque table du schéma en étoile en CSV."""
    POWERBI_DIR.mkdir(parents=True, exist_ok=True)
    for name in POWERBI_EXPORTS + STAR_TABLES:
        df = pd.read_sql(f"SELECT * FROM {name}", engine)
        df.to_csv(POWERBI_DIR / f"{name}.csv", index=False)
        log.info("Export Power BI : %-22s %7d lignes", name, len(df))


def save_chart(fig, name: str) -> None:
    """Enregistre un graphique dans reports/."""
    fig.tight_layout()
    fig.savefig(REPORTS_DIR / name, dpi=120)
    plt.close(fig)
    log.info("Graphique créé : reports/%s", name)


def chart_monthly_admissions(engine) -> None:
    df = pd.read_sql("""SELECT date_trunc('month', admission_date) AS month, SUM(admissions) AS admissions,
                        ROUND(SUM(avg_waiting_time * admissions) / SUM(admissions), 1) AS wait
                        FROM vw_daily_kpis GROUP BY 1 ORDER BY 1""", engine)
    df = df.iloc[1:-1]  # on retire les mois incomplets (premier et dernier)
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(df["month"], df["admissions"], color="#1f77b4", marker="o", markersize=3)
    ax.set_title("Admissions par mois")
    ax.set_ylabel("Admissions")
    ax.grid(alpha=0.3)
    save_chart(fig, "01_admissions_par_mois.png")


def chart_emergency_hours(engine) -> None:
    df = pd.read_sql("SELECT * FROM vw_emergency_hourly ORDER BY hour", engine)
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.bar(df["hour"], df["admissions"], color="#d62728")
    ax.set_title("Urgences : arrivées par heure (heures de pointe à 11 h et 19 h)")
    ax.set_xlabel("Heure d'arrivée")
    ax.set_ylabel("Admissions")
    ax.set_xticks(range(24))
    save_chart(fig, "02_urgences_heures_de_pointe.png")


def chart_staff_vs_waiting(engine) -> None:
    df = pd.read_sql("""SELECT staff_on_duty, ROUND(AVG(avg_waiting_time), 1) AS wait, COUNT(*) AS n
                        FROM vw_staff_load WHERE department_name = 'Emergency'
                        GROUP BY staff_on_duty ORDER BY staff_on_duty""", engine)
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.bar(df["staff_on_duty"].astype(str), df["wait"], color="#ff7f0e")
    ax.set_title("Urgences : moins de personnel = plus d'attente")
    ax.set_xlabel("Personnel présent dans la journée")
    ax.set_ylabel("Attente moyenne (min)")
    save_chart(fig, "03_personnel_vs_attente.png")


def chart_departments(engine) -> None:
    df = pd.read_sql("SELECT * FROM vw_department_kpis ORDER BY admissions DESC", engine)
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    axes[0].barh(df["department_name"], df["admissions"], color="#2ca02c")
    axes[0].set_title("Admissions par service")
    axes[1].barh(df["department_name"], df["avg_waiting_time"], color="#9467bd")
    axes[1].set_title("Attente moyenne par service (min)")
    for ax in axes:
        ax.invert_yaxis()
    save_chart(fig, "04_services.png")


def main() -> None:
    engine = get_engine()
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    export_for_powerbi(engine)
    chart_monthly_admissions(engine)
    chart_emergency_hours(engine)
    chart_staff_vs_waiting(engine)
    chart_departments(engine)


if __name__ == "__main__":
    main()
