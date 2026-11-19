"""
Interface web de la plateforme : tableaux de bord, suivi de la pipeline et assistant IA,
le tout dans le navigateur, sans terminal. Lit les données du Data Warehouse PostgreSQL.
Lancement : streamlit run dashboard/app.py   (puis ouvrir http://localhost:8501)

Auteures : Hanae MAYTA et Wafae ZALOUK
"""
import sys
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # pour importer src/
from src.agent.sql_agent import EXAMPLES, answer_with_mode, llm_enabled  # noqa: E402
from src.config import LLM_MODEL, LLM_PROVIDER, REPORTS_DIR, get_engine  # noqa: E402

BLUE, LIGHT_BLUE, RED, GRAY = "#2B6CB0", "#9CC3E6", "#D62839", "#5B6B7D"

st.set_page_config(page_title="Hospital Operations Intelligence", page_icon="🏥", layout="wide")


# ======================= ACCÈS AUX DONNÉES =======================

@st.cache_resource
def engine():
    return get_engine()


@st.cache_data(ttl=300)
def query(sql: str) -> pd.DataFrame:
    """Exécute une requête de lecture et met le résultat en cache 5 minutes."""
    return pd.read_sql(sql, engine())


def database_ok() -> bool:
    try:
        query("SELECT 1")
        return True
    except Exception:
        return False


# ======================= PETITS OUTILS D'AFFICHAGE =======================

def fmt(n: float, decimals: int = 0) -> str:
    """Nombre au format français : 50 398 / 32,1."""
    text = f"{n:,.{decimals}f}".replace(",", " ").replace(".", ",")
    return text


def hbar(df: pd.DataFrame, x: str, y: str, title: str, unit: str = "", highlight: str | None = None,
         number_format: str = ",.1f"):
    """Barres horizontales triées, avec une barre mise en avant en rouge."""
    color = (alt.condition(alt.datum[y] == highlight, alt.value(RED), alt.value(BLUE))
             if highlight else alt.value(BLUE))
    bars = alt.Chart(df).mark_bar(cornerRadiusEnd=3).encode(
        x=alt.X(f"{x}:Q", title=unit or None),
        y=alt.Y(f"{y}:N", sort="-x", title=None, axis=alt.Axis(labelOverlap=False, labelLimit=150)),
        color=color,
        tooltip=[y, alt.Tooltip(x, format=number_format)],
    )
    labels = bars.mark_text(align="left", dx=4, color=GRAY).encode(
        text=alt.Text(f"{x}:Q", format=number_format), color=alt.value(GRAY))
    return (bars + labels).properties(title=title, height=260)


def section_title(icon: str, title: str, subtitle: str):
    st.markdown(f"## {icon} {title}")
    st.caption(subtitle)


# ======================= PAGE 1 : VUE D'ENSEMBLE =======================

def page_overview():
    section_title("🏥", "Vue d'ensemble", "Les indicateurs clés de l'hôpital, calculés sur les données propres.")
    kpi = query("""
        SELECT COUNT(DISTINCT patient_id) AS patients, COUNT(*) AS admissions,
               AVG(waiting_time) AS attente, AVG(length_of_stay) AS sejour,
               COUNT(*)::numeric / COUNT(DISTINCT admission_date) AS par_jour
        FROM fact_admission""").iloc[0]
    c = st.columns(5)
    c[0].metric("Patients", fmt(kpi.patients))
    c[1].metric("Admissions", fmt(kpi.admissions))
    c[2].metric("Admissions / jour", fmt(kpi.par_jour, 1))
    c[3].metric("Attente moyenne", f"{fmt(kpi.attente, 1)} min")
    c[4].metric("Durée de séjour", f"{fmt(kpi.sejour, 1)} jours")

    monthly = query("""
        SELECT date_trunc('month', admission_date)::date AS mois, COUNT(*) AS admissions,
               ROUND(AVG(waiting_time), 1) AS attente
        FROM fact_admission GROUP BY 1 ORDER BY 1""").iloc[1:-1]   # mois incomplets retirés
    line = alt.Chart(monthly).mark_line(color=BLUE, point=alt.OverlayMarkDef(size=18, color=BLUE)).encode(
        x=alt.X("mois:T", title=None), y=alt.Y("admissions:Q", title="Admissions", scale=alt.Scale(zero=False)),
        tooltip=[alt.Tooltip("mois:T", format="%B %Y"), "admissions", "attente"],
    ).properties(title="Admissions par mois", height=260)
    st.altair_chart(line, use_container_width=True)

    dep = query("SELECT department_name AS service, admissions, avg_waiting_time AS attente FROM vw_department_kpis")
    left, right = st.columns(2)
    left.altair_chart(hbar(dep, "admissions", "service", "Admissions par service", highlight="Emergency",
                           number_format=",.0f"),
                      use_container_width=True)
    right.altair_chart(hbar(dep, "attente", "service", "Attente moyenne par service", "minutes",
                            highlight="Emergency"), use_container_width=True)


# ======================= PAGE 2 : URGENCES & PERSONNEL =======================

def page_emergency():
    section_title("🚑", "Urgences et personnel",
                  "Quand les urgences sont-elles saturées, et quel est l'effet du personnel sur l'attente ?")
    hourly = query("SELECT hour AS heure, admissions, avg_waiting_time AS attente FROM vw_emergency_hourly ORDER BY hour")
    peaks = hourly.nlargest(3, "admissions")["heure"].tolist()
    hourly["pic"] = hourly["heure"].isin(peaks)
    chart = alt.Chart(hourly).mark_bar().encode(
        x=alt.X("heure:O", title="Heure d'arrivée", axis=alt.Axis(labelAngle=0)), y=alt.Y("admissions:Q", title="Admissions"),
        color=alt.condition(alt.datum.pic, alt.value(RED), alt.value(BLUE)),
        tooltip=["heure", "admissions", "attente"],
    ).properties(title="Arrivées aux urgences par heure (heures de pointe en rouge)", height=280)
    st.altair_chart(chart, use_container_width=True)

    left, right = st.columns(2)
    staff = query("""
        SELECT staff_on_duty AS soignants, ROUND(AVG(avg_waiting_time), 1) AS attente, COUNT(*) AS jours
        FROM vw_staff_load WHERE department_name = 'Emergency'
        GROUP BY staff_on_duty ORDER BY staff_on_duty""")
    bars = alt.Chart(staff).mark_bar(color=BLUE).encode(
        x=alt.X("soignants:O", title="Soignants présents dans la journée", axis=alt.Axis(labelAngle=0)),
        y=alt.Y("attente:Q", title="Attente moyenne (min)"), tooltip=["soignants", "attente", "jours"],
    ).properties(title="Urgences : moins de personnel = plus d'attente", height=280)
    left.altair_chart(bars, use_container_width=True)

    load = query("""
        SELECT CASE WHEN patients_per_staff < 1 THEN '1. moins de 1'
                    WHEN patients_per_staff < 2 THEN '2. de 1 à 2'
                    WHEN patients_per_staff < 4 THEN '3. de 2 à 4'
                    ELSE '4. 4 et plus' END AS charge,
               ROUND(AVG(avg_waiting_time), 1) AS attente
        FROM vw_staff_load GROUP BY 1 ORDER BY 1""")
    load["charge"] = load["charge"].str[3:]
    bars = alt.Chart(load).mark_bar(color=RED).encode(
        x=alt.X("charge:N", sort=None, title="Patients par soignant", axis=alt.Axis(labelAngle=0)),
        y=alt.Y("attente:Q", title="Attente moyenne (min)"), tooltip=["charge", "attente"],
    ).properties(title="Tous services : attente selon la charge du personnel", height=280)
    right.altair_chart(bars, use_container_width=True)

    occ = query("""SELECT department_name AS service, ROUND(AVG(occupancy_rate_pct), 1) AS occupation
                   FROM vw_daily_occupancy GROUP BY 1""")
    st.altair_chart(hbar(occ, "occupation", "service", "Taux d'occupation moyen des lits", "%",
                         highlight=occ.loc[occ["occupation"].idxmax(), "service"]), use_container_width=True)


# ======================= PAGE 3 : PRÉVISION & ANOMALIES =======================

def page_prediction():
    section_title("🔮", "Prévision et alertes",
                  "Machine Learning : admissions prévues pour demain et jours anormaux détectés.")
    forecast = query("SELECT full_date, actual, predicted, is_next_day FROM ml_forecast ORDER BY full_date")
    capacity = int(query("SELECT SUM(daily_capacity) AS c FROM dim_department")["c"][0])
    nxt = forecast[forecast["is_next_day"]].iloc[0]
    ratio = float(nxt["predicted"]) / capacity

    c = st.columns(3)
    c[0].metric(f"Prévision pour le {nxt['full_date']}", f"{fmt(nxt['predicted'], 1)} admissions")
    c[1].metric("Capacité quotidienne", f"{capacity} admissions")
    c[2].metric("Charge prévue", f"{ratio:.0%}")
    if ratio > 1:
        st.error("🚨 Alerte surcharge : la prévision dépasse la capacité. Renforcer le personnel.")
    elif ratio > 0.85:
        st.warning("⚠️ Vigilance : la prévision approche de la capacité.")
    else:
        st.success("✅ Pas de surcharge prévue pour demain.")

    hist = forecast[~forecast["is_next_day"]].tail(120).melt(
        id_vars="full_date", value_vars=["actual", "predicted"], var_name="série", value_name="admissions")
    hist["série"] = hist["série"].map({"actual": "Réel", "predicted": "Prédit"})
    line = alt.Chart(hist).mark_line().encode(
        x=alt.X("full_date:T", title=None), y=alt.Y("admissions:Q", title="Admissions"),
        color=alt.Color("série:N", scale=alt.Scale(range=[BLUE, RED]), legend=alt.Legend(orient="top", title=None)),
    ).properties(title="Admissions réelles et prédites (120 derniers jours)", height=300)
    st.altair_chart(line, use_container_width=True)

    anomalies = query("""SELECT full_date AS jour, admissions, avg_waiting_time AS attente_min,
                                staff_on_duty AS soignants, anomaly_score AS score
                         FROM ml_daily_anomalies WHERE is_anomaly ORDER BY anomaly_score""")
    st.markdown(f"**{len(anomalies)} jours anormaux détectés par l'Isolation Forest** (du plus au moins anormal)")
    st.dataframe(anomalies, hide_index=True, use_container_width=True)


# ======================= PAGE 4 : PIPELINE =======================

def page_pipeline():
    section_title("⚙️", "Pipeline de données",
                  "Extract → Transform → Validate → Load → Quality check. Historique, contrôles qualité et lancement.")
    steps = st.columns(5)
    for col, (name, text) in zip(steps, [("Extract", "lire les 4 CSV"), ("Transform", "nettoyer + calculer"),
                                         ("Validate", "28 contrôles"), ("Load", "upsert PostgreSQL"),
                                         ("Quality check", "vérifier la base")]):
        col.info(f"**{name}**\n\n{text}")

    left, right = st.columns(2)
    if left.button("▶️ Lancer la pipeline", use_container_width=True, type="primary"):
        run_pipeline_from_ui(simulate_bad_data=False)
    if right.button("🧪 Simuler des données invalides", use_container_width=True):
        run_pipeline_from_ui(simulate_bad_data=True)

    runs = query("""SELECT run_id AS "n°", to_char(run_date, 'DD/MM/YYYY HH24:MI') AS date, status AS statut,
                           rows_loaded AS lignes, ROUND(duration_seconds, 1)::float AS "durée (s)", message
                    FROM pipeline_runs ORDER BY run_id DESC LIMIT 10""")
    st.markdown("**Dernières exécutions** (table `pipeline_runs`)")
    st.dataframe(runs.style.map(lambda v: f"color: {RED}; font-weight: bold" if v == "FAILED" else
                                ("color: #1E8449; font-weight: bold" if v == "SUCCESS" else ""), subset=["statut"]),
                 hide_index=True, use_container_width=True)

    report = REPORTS_DIR / "data_quality_report.md"
    with st.expander("📋 Rapport de qualité des données (dernière validation)", expanded=False):
        st.markdown(report.read_text(encoding="utf-8") if report.exists() else "Pas encore de rapport.")


def run_pipeline_from_ui(simulate_bad_data: bool):
    from src.pipeline import run_pipeline
    label = "Pipeline en cours avec des données invalides…" if simulate_bad_data else "Pipeline en cours (≈ 30 s)…"
    with st.spinner(label):
        try:
            rows = run_pipeline(simulate_bad_data=simulate_bad_data)
            st.success(f"✅ Pipeline terminée : {fmt(rows)} lignes chargées, 28 contrôles réussis.")
        except Exception as exc:
            st.error(f"❌ Pipeline arrêtée, rien n'a été chargé.\n\n{exc}")
    st.cache_data.clear()


# ======================= PAGE 5 : ASSISTANT IA =======================

def page_assistant():
    section_title("🤖", "Assistant IA", "Posez une question en français ou en anglais : l'IA écrit le SQL, "
                                       "notre code le vérifie, la base répond.")
    if llm_enabled():
        st.caption(f"Mode : **LLM** ({LLM_PROVIDER} / {LLM_MODEL}) — repli automatique sur les questions préparées.")
    else:
        st.caption("Mode : **questions préparées** (aucun LLM configuré dans `.env`).")

    if "history" not in st.session_state:
        st.session_state.history = []

    st.markdown("**Exemples :**")
    cols = st.columns(3)
    clicked = None
    for i, q in enumerate(EXAMPLES):
        if cols[i % 3].button(q, key=f"ex{i}", use_container_width=True):
            clicked = q

    for msg in st.session_state.history:
        show_message(msg)

    question = st.chat_input("Votre question… ex : Quel service fait le plus attendre ses patients ?") or clicked
    if question:
        with st.spinner("Réflexion…"):
            try:
                sql, df, text, mode = answer_with_mode(question)
                msg = {"question": question, "text": text, "sql": sql, "df": df, "mode": mode}
            except Exception as exc:
                msg = {"question": question, "text": f"⛔ {exc}", "sql": None, "df": None, "mode": None}
        st.session_state.history.append(msg)
        show_message(msg)


def show_message(msg: dict):
    with st.chat_message("user"):
        st.write(msg["question"])
    with st.chat_message("assistant", avatar="🤖"):
        st.write(msg["text"])
        if msg["sql"]:
            source = "réponse du LLM" if msg["mode"] == "llm" else "question préparée (sans LLM)"
            with st.expander(f"Voir le SQL et le résultat — {source}"):
                st.code(msg["sql"], language="sql")
                st.dataframe(msg["df"].head(20), hide_index=True, use_container_width=True)


# ======================= NAVIGATION =======================

PAGES = {
    "🏥 Vue d'ensemble": page_overview,
    "🚑 Urgences et personnel": page_emergency,
    "🔮 Prévision et alertes": page_prediction,
    "⚙️ Pipeline": page_pipeline,
    "🤖 Assistant IA": page_assistant,
}

with st.sidebar:
    st.markdown("### Hospital Operations\n### Intelligence Platform")
    st.caption("Hanae MAYTA · Wafae ZALOUK\n\nUMLP · M2 Technologies de l'Information")
    choice = st.radio("Navigation", list(PAGES), label_visibility="collapsed")
    if st.button("🔄 Rafraîchir les données", use_container_width=True):
        st.cache_data.clear()

if not database_ok():
    st.error("Impossible de se connecter à PostgreSQL. Lancez `docker compose up -d`, "
             "puis la pipeline (`python -m src.pipeline`), et rechargez la page.")
    st.stop()

try:
    PAGES[choice]()
except Exception as exc:  # table absente : une étape n'a pas encore été lancée
    st.warning(f"Données manquantes pour cette page ({exc.__class__.__name__}). "
               "Lancez d'abord : `python -m src.pipeline`, `python -m src.ml.forecast`, `python -m src.ml.anomaly`.")
