"""
Détection des JOURS ANORMAUX avec Isolation Forest (volume, attente, charge du personnel).
Résultats sauvegardés dans reports/anomalies.csv et dans la table ml_daily_anomalies.
Affiche aussi une ALERTE DE SURCHARGE si la prévision de demain dépasse la capacité.
Usage : python -m src.ml.anomaly   (lancer forecast avant pour l'alerte)

Auteures : Hanae MAYTA et Wafae ZALOUK
"""
import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.ensemble import IsolationForest  # noqa: E402
from sqlalchemy import text  # noqa: E402

from src.config import POWERBI_DIR, REPORTS_DIR, get_engine, get_logger  # noqa: E402

log = get_logger("anomaly")
FEATURES = ["admissions", "avg_waiting_time", "avg_patients_per_staff", "staff_on_duty"]
CONTAMINATION = 0.01  # on suppose ~1 % de jours anormaux
WARNING_LEVEL = 0.85  # 85 % de la capacité = vigilance


def load_daily_features(engine) -> pd.DataFrame:
    """Une ligne par jour : volume, attente, charge moyenne, personnel présent."""
    return pd.read_sql("""
        SELECT k.admission_date AS full_date, k.admissions::int AS admissions, k.avg_waiting_time,
               k.staff_on_duty::int AS staff_on_duty,
               ROUND(AVG(s.patients_per_staff), 2) AS avg_patients_per_staff
        FROM vw_daily_kpis k JOIN vw_staff_load s USING (admission_date)
        GROUP BY k.admission_date, k.admissions, k.avg_waiting_time, k.staff_on_duty
        ORDER BY k.admission_date""", engine)


def detect(df: pd.DataFrame) -> pd.DataFrame:
    """Entraîne l'Isolation Forest et marque les jours anormaux."""
    model = IsolationForest(contamination=CONTAMINATION, random_state=42)
    model.fit(df[FEATURES])
    df = df.copy()
    df["anomaly_score"] = model.decision_function(df[FEATURES]).round(4)  # plus bas = plus anormal
    df["is_anomaly"] = model.predict(df[FEATURES]) == -1
    return df


def save_results(df: pd.DataFrame, engine) -> None:
    """CSV + table SQL (remplacée à chaque exécution, dans une transaction)."""
    df.to_csv(REPORTS_DIR / "anomalies.csv", index=False)
    POWERBI_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(POWERBI_DIR / "ml_daily_anomalies.csv", index=False)
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM ml_daily_anomalies"))
        df[["full_date"] + FEATURES[:1] + ["avg_waiting_time", "avg_patients_per_staff",
                                            "staff_on_duty", "anomaly_score", "is_anomaly"]] \
            .to_sql("ml_daily_anomalies", conn, if_exists="append", index=False)


def plot(df: pd.DataFrame) -> None:
    """Admissions quotidiennes avec les jours anormaux en rouge."""
    fig, ax = plt.subplots(figsize=(11, 4))
    ax.plot(df["full_date"], df["admissions"], color="#7f7f7f", linewidth=0.6, label="Admissions/jour")
    anomalies = df[df["is_anomaly"]]
    ax.scatter(anomalies["full_date"], anomalies["admissions"], color="red", zorder=3,
               label=f"Jour anormal ({len(anomalies)})")
    ax.set_title("Détection d'anomalies (Isolation Forest)")
    ax.legend()
    fig.tight_layout()
    fig.savefig(REPORTS_DIR / "06_anomalies.png", dpi=120)
    plt.close(fig)


def overload_alert() -> str:
    """Compare la prévision de demain à la capacité quotidienne de l'hôpital."""
    path = REPORTS_DIR / "forecast_next_day.json"
    if not path.exists():
        return "Pas de prévision disponible : lancez d'abord `python -m src.ml.forecast`."
    f = json.loads(path.read_text(encoding="utf-8"))
    ratio = f["forecast_admissions"] / f["hospital_daily_capacity"]
    msg = (f"{f['date']} : {f['forecast_admissions']} admissions prévues pour une capacité de "
           f"{f['hospital_daily_capacity']}/jour ({ratio:.0%})")
    if ratio > 1:
        return f"🚨 ALERTE SURCHARGE - {msg}. Renforcer le personnel !"
    if ratio > WARNING_LEVEL:
        return f"⚠️  VIGILANCE - {msg}."
    return f"✅ Pas de surcharge prévue - {msg}."


def main() -> pd.DataFrame:
    engine = get_engine()
    df = detect(load_daily_features(engine))
    save_results(df, engine)
    plot(df)
    log.info("%d jours anormaux détectés sur %d. Les 5 plus marqués :", df["is_anomaly"].sum(), len(df))
    top = df[df["is_anomaly"]].nsmallest(5, "anomaly_score")
    for _, row in top.iterrows():
        log.info("   %s : %3d admissions, attente %5.1f min, %2d soignants",
                 row["full_date"], row["admissions"], row["avg_waiting_time"], row["staff_on_duty"])
    log.info(overload_alert())
    return df


if __name__ == "__main__":
    main()
