"""
Prévision du nombre d'admissions du LENDEMAIN avec un GradientBoosting (features calendaires
+ retards/lags), comparé à deux modèles naïfs. Métriques MAE/RMSE, graphique réel vs prédit,
et prévision pour demain sauvegardée dans reports/forecast_next_day.json.
Usage : python -m src.ml.forecast

Auteures : Hanae MAYTA et Wafae ZALOUK
"""
import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.ensemble import GradientBoostingRegressor  # noqa: E402
from sklearn.metrics import mean_absolute_error, mean_squared_error  # noqa: E402

from sqlalchemy import text  # noqa: E402

from src.config import POWERBI_DIR, PROCESSED_DIR, REPORTS_DIR, get_engine, get_logger  # noqa: E402

log = get_logger("forecast")
FEATURES = ["day_of_week", "month", "day_of_year", "is_weekend",
            "lag_1", "lag_7", "rolling_mean_7", "rolling_mean_28"]
TEST_DAYS = 365  # la dernière année sert de test (jamais vue à l'entraînement)


def load_daily() -> pd.DataFrame:
    """Indicateurs quotidiens depuis le Data Warehouse (repli sur le CSV si la base est absente)."""
    try:
        df = pd.read_sql("SELECT * FROM vw_daily_kpis ORDER BY admission_date", get_engine())
    except Exception as exc:
        log.warning("Base indisponible (%s) -> lecture de data/processed/fact_admission.csv", exc)
        fact = pd.read_csv(PROCESSED_DIR / "fact_admission.csv")
        df = fact.groupby("admission_date").agg(admissions=("admission_id", "size"),
                                                avg_waiting_time=("waiting_time", "mean")).reset_index()
        df["hospital_daily_capacity"] = 43
    df["admission_date"] = pd.to_datetime(df["admission_date"])
    return df.set_index("admission_date").asfreq("D", fill_value=0)


def make_features(admissions: pd.Series) -> pd.DataFrame:
    """Crée les features. Les lags utilisent uniquement le PASSÉ (pas de fuite d'information)."""
    df = pd.DataFrame({"admissions": admissions})
    idx = df.index
    df["day_of_week"] = idx.dayofweek
    df["month"] = idx.month
    df["day_of_year"] = idx.dayofyear
    df["is_weekend"] = (idx.dayofweek >= 5).astype(int)
    df["lag_1"] = df["admissions"].shift(1)
    df["lag_7"] = df["admissions"].shift(7)
    df["rolling_mean_7"] = df["admissions"].shift(1).rolling(7).mean()
    df["rolling_mean_28"] = df["admissions"].shift(1).rolling(28).mean()
    return df


def scores(y_true, y_pred) -> dict:
    """MAE et RMSE arrondis."""
    return {"MAE": round(mean_absolute_error(y_true, y_pred), 2),
            "RMSE": round(float(np.sqrt(mean_squared_error(y_true, y_pred))), 2)}


def train_and_evaluate(data: pd.DataFrame):
    """Entraîne sur le passé, évalue sur la dernière année, compare aux baselines."""
    data = data.dropna()
    train, test = data.iloc[:-TEST_DAYS], data.iloc[-TEST_DAYS:]
    model = GradientBoostingRegressor(n_estimators=200, max_depth=3, learning_rate=0.05,
                                      random_state=42)
    model.fit(train[FEATURES], train["admissions"])
    pred = model.predict(test[FEATURES])
    metrics = {
        "Baseline naïve (= hier)": scores(test["admissions"], test["lag_1"]),
        "Baseline moyenne 7 jours": scores(test["admissions"], test["rolling_mean_7"]),
        "GradientBoosting": scores(test["admissions"], pred),
    }
    return model, test.assign(prediction=pred), metrics


def predict_next_day(data: pd.DataFrame) -> tuple[pd.Timestamp, float]:
    """Réentraîne sur TOUT l'historique puis prédit le jour suivant la dernière date."""
    next_day = data.index.max() + pd.Timedelta(days=1)
    extended = make_features(pd.concat([data["admissions"], pd.Series([np.nan], index=[next_day])]))
    model = GradientBoostingRegressor(n_estimators=200, max_depth=3, learning_rate=0.05,
                                      random_state=42)
    train = extended.iloc[:-1].dropna()
    model.fit(train[FEATURES], train["admissions"])
    return next_day, float(model.predict(extended.iloc[[-1]][FEATURES])[0])


def plot(test: pd.DataFrame) -> None:
    """Graphique réel vs prédit sur les 120 derniers jours."""
    last = test.iloc[-120:]
    fig, ax = plt.subplots(figsize=(11, 4))
    ax.plot(last.index, last["admissions"], label="Réel", color="#1f77b4")
    ax.plot(last.index, last["prediction"], label="Prédit (GradientBoosting)", color="#ff7f0e")
    ax.set_title("Admissions quotidiennes : réel vs prédit (120 derniers jours du test)")
    ax.legend()
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(REPORTS_DIR / "05_forecast_reel_vs_predit.png", dpi=120)
    plt.close(fig)


def save_predictions(test: pd.DataFrame, next_day: pd.Timestamp, forecast: float) -> None:
    """Sauvegarde réel vs prédit + prévision de demain (table ml_forecast + CSV pour Power BI)."""
    out = pd.DataFrame({"full_date": test.index.date, "actual": test["admissions"].astype(int),
                        "predicted": test["prediction"].round(2), "is_next_day": False})
    future = pd.DataFrame([{"full_date": next_day.date(), "actual": None,
                            "predicted": round(forecast, 2), "is_next_day": True}])
    out = pd.concat([out, future], ignore_index=True)
    POWERBI_DIR.mkdir(parents=True, exist_ok=True)
    out.to_csv(POWERBI_DIR / "ml_forecast.csv", index=False)
    try:
        with get_engine().begin() as conn:
            conn.execute(text("DELETE FROM ml_forecast"))
            out.to_sql("ml_forecast", conn, if_exists="append", index=False)
    except Exception as exc:
        log.warning("Prévisions non écrites en base (%s) : CSV uniquement", exc)


def main() -> dict:
    daily = load_daily()
    data = make_features(daily["admissions"])
    _, test, metrics = train_and_evaluate(data)
    for name, m in metrics.items():
        log.info("%-26s MAE = %5.2f | RMSE = %5.2f", name, m["MAE"], m["RMSE"])

    next_day, forecast = predict_next_day(data)
    capacity = int(daily["hospital_daily_capacity"].max())
    result = {"date": str(next_day.date()), "forecast_admissions": round(forecast, 1),
              "hospital_daily_capacity": capacity, "metrics": metrics}
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    (REPORTS_DIR / "forecast_next_day.json").write_text(json.dumps(result, indent=2, ensure_ascii=False),
                                                        encoding="utf-8")
    plot(test)
    save_predictions(test, next_day, forecast)
    log.info("Prévision pour le %s : %.1f admissions (capacité %d/jour)", next_day.date(), forecast, capacity)
    return result


if __name__ == "__main__":
    main()
