"""
Agent IA "question en langage naturel -> SQL -> réponse" sur le Data Warehouse.
Deux modes : (a) avec LLM (Ollama local et gratuit, Claude, ou API compatible OpenAI) selon
LLM_PROVIDER dans .env, (b) mode SANS LLM basé sur
des modèles de questions (la démo marche toujours). Sécurité : SELECT uniquement, lecture seule,
liste blanche de tables, limite de lignes et délai maximum.

Auteures : Hanae MAYTA et Wafae ZALOUK
Usage : python -m src.agent.sql_agent "Quel service a le plus d'admissions ?"
        python -m src.agent.sql_agent --examples      (lance les 9 questions d'exemple)
        python -m src.agent.sql_agent                 (mode interactif)
"""
import argparse
import json
import re
import urllib.request

import pandas as pd
from sqlalchemy import text

from src.config import (ANTHROPIC_API_KEY, LLM_API_KEY, LLM_BASE_URL, LLM_MODEL, LLM_PROVIDER,
                        get_engine, get_logger)

log = get_logger("agent")

# ======================= SÉCURITÉ =======================
ALLOWED_TABLES = {
    "fact_admission", "dim_patient", "dim_date", "dim_department", "dim_staff",
    "vw_admissions_detail", "vw_daily_kpis", "vw_staff_load", "vw_emergency_hourly",
    "vw_department_kpis", "vw_daily_occupancy", "vw_readmissions", "ml_daily_anomalies", "ml_forecast",
}
FORBIDDEN_WORDS = ["insert", "update", "delete", "drop", "alter", "create", "truncate", "grant",
                   "revoke", "copy", "execute", "call", "merge", "vacuum", "pg_sleep", "set", "into"]
MAX_ROWS = 200


def is_safe_sql(sql: str) -> tuple[bool, str]:
    """Vérifie qu'une requête est un SELECT en lecture seule sur des tables autorisées."""
    query = sql.strip().rstrip(";").strip()
    lowered = query.lower()
    if ";" in query:
        return False, "une seule requête autorisée"
    if "--" in query or "/*" in query:
        return False, "commentaires SQL interdits"
    if not re.match(r"^(select|with)\b", lowered):
        return False, "seules les requêtes SELECT sont autorisées"
    for word in FORBIDDEN_WORDS:
        if re.search(rf"\b{word}\b", lowered):
            return False, f"mot-clé interdit : {word.upper()}"
    cte_names = set(re.findall(r"(\w+)\s+as\s*\(", lowered))           # tables temporaires du WITH
    used = set(re.findall(r"\b(?:from|join)\s+([a-z_][a-z0-9_]*)", lowered))
    unknown = used - ALLOWED_TABLES - cte_names
    if unknown:
        return False, f"table(s) non autorisée(s) : {sorted(unknown)}"
    return True, "ok"


def run_query(sql: str, engine=None) -> pd.DataFrame:
    """Exécute un SELECT validé dans une transaction en LECTURE SEULE, avec limite et délai."""
    safe, reason = is_safe_sql(sql)
    if not safe:
        raise ValueError(f"Requête refusée : {reason}")
    engine = engine or get_engine()
    query = f"SELECT * FROM ({sql.strip().rstrip(';')}) AS q LIMIT {MAX_ROWS}"
    with engine.connect() as conn:
        with conn.begin():
            conn.execute(text("SET TRANSACTION READ ONLY"))
            conn.execute(text("SET LOCAL statement_timeout = 10000"))   # 10 s maximum
            return pd.read_sql(text(query), conn)


# ======================= MODE SANS CLÉ : modèles de questions =======================

def is_english(question: str) -> bool:
    """Détection très simple de la langue."""
    words = set(re.findall(r"[a-z']+", question.lower()))
    return len(words & {"what", "which", "how", "why", "the", "is", "are", "average", "many",
                        "was", "per", "by", "show", "yesterday"}) >= 2


def pct(new: float, old: float) -> str:
    """Variation en pourcentage, avec signe."""
    return f"{(new - old) / old * 100:+.0f} %" if old else "n/a"


def explain_why_wait(df: pd.DataFrame, en: bool) -> str:
    """Construit l'explication de 'Pourquoi le temps d'attente était élevé hier ?'."""
    r = df.iloc[0]
    causes = []
    if r["admissions"] > 1.2 * r["prev_admissions"]:
        causes.append((f"admissions {pct(r['admissions'], r['prev_admissions'])}" if en else
                       f"un afflux de patients ({r['admissions']} admissions, {pct(r['admissions'], r['prev_admissions'])})"))
    if r["er_staff"] < 0.85 * r["prev_er_staff"]:
        causes.append((f"emergency staff {pct(r['er_staff'], r['prev_er_staff'])}" if en else
                       f"un sous-effectif aux urgences ({r['er_staff']} soignants au lieu de {r['prev_er_staff']}, "
                       f"{pct(r['er_staff'], r['prev_er_staff'])})"))
    if r["is_anomaly"]:
        causes.append("flagged as anomaly by Isolation Forest" if en else
                      "un jour classé ANORMAL par l'Isolation Forest")
    if en:
        return (f"On {r['day']}, average waiting time was {r['avg_waiting_time']} min vs "
                f"{r['prev_wait']} min over the previous 7 days ({pct(r['avg_waiting_time'], r['prev_wait'])}); "
                f"main causes: {', '.join(causes) or 'no clear cause'}.")
    return (f"Le {r['day']} (dernier jour de l'entrepôt), l'attente moyenne était de {r['avg_waiting_time']} min "
            f"contre {r['prev_wait']} min les 7 jours précédents ({pct(r['avg_waiting_time'], r['prev_wait'])}), "
            f"à cause de : {', '.join(causes) or 'aucune cause nette'}.")


WHY_WAIT_SQL = """
WITH last_day AS (SELECT MAX(admission_date) AS d FROM vw_daily_kpis),
yesterday AS (
    SELECT k.admission_date, k.admissions, k.avg_waiting_time, s.staff_on_duty AS er_staff
    FROM vw_daily_kpis k
    JOIN vw_staff_load s ON s.admission_date = k.admission_date AND s.department_name = 'Emergency'
    WHERE k.admission_date = (SELECT d FROM last_day)),
previous AS (
    SELECT ROUND(AVG(k.admissions), 1) AS prev_admissions, ROUND(AVG(k.avg_waiting_time), 1) AS prev_wait,
           ROUND(AVG(s.staff_on_duty), 1) AS prev_er_staff
    FROM vw_daily_kpis k
    JOIN vw_staff_load s ON s.admission_date = k.admission_date AND s.department_name = 'Emergency'
    WHERE k.admission_date BETWEEN (SELECT d FROM last_day) - 7 AND (SELECT d FROM last_day) - 1)
SELECT y.admission_date::text AS day, y.admissions::int AS admissions, p.prev_admissions,
       y.avg_waiting_time, p.prev_wait, y.er_staff, p.prev_er_staff,
       COALESCE(a.is_anomaly, false) AS is_anomaly
FROM yesterday y CROSS JOIN previous p
LEFT JOIN ml_daily_anomalies a ON a.full_date = y.admission_date
"""

# Chaque modèle : mots-clés à trouver (tous les groupes doivent matcher), SQL, explication FR/EN.
# L'ordre compte : les questions les plus précises sont testées en premier.
TEMPLATES = [
    {
        "keywords": [r"pourquoi|why", r"attente|attend|wait"],
        "sql": WHY_WAIT_SQL,
        "explain": explain_why_wait,
    },
    {
        "keywords": [r"heure|hour|pointe|peak"],
        "sql": "SELECT hour, admissions, avg_waiting_time FROM vw_emergency_hourly ORDER BY admissions DESC LIMIT 3",
        "explain": lambda df, en: (
            f"Emergency peak hours are {', '.join(f'{h}h' for h in df['hour'])}." if en else
            f"Les heures de pointe des urgences sont {', '.join(f'{h} h' for h in df['hour'])} "
            f"({df['admissions'].iloc[0]} arrivées à {df['hour'].iloc[0]} h)."),
    },
    {
        "keywords": [r"r[ée]admi|readmi"],
        "sql": """SELECT (SELECT COUNT(*) FROM vw_readmissions) AS readmissions,
                  ROUND(100.0 * (SELECT COUNT(*) FROM vw_readmissions) / COUNT(*), 2) AS rate_pct
                  FROM fact_admission""",
        "explain": lambda df, en: (
            f"{df['readmissions'][0]} readmissions within 30 days, i.e. {df['rate_pct'][0]} % of admissions." if en else
            f"{df['readmissions'][0]} réadmissions à moins de 30 jours, soit {df['rate_pct'][0]} % des admissions."),
    },
    {
        "keywords": [r"anomal|anorma"],
        "sql": """SELECT full_date, admissions, avg_waiting_time, staff_on_duty FROM ml_daily_anomalies
                  WHERE is_anomaly ORDER BY anomaly_score LIMIT 5""",
        "explain": lambda df, en: (
            f"The most abnormal day was {df['full_date'][0]} ({df['admissions'][0]} admissions)." if en else
            f"Le jour le plus anormal est le {df['full_date'][0]} ({df['admissions'][0]} admissions, "
            f"{df['avg_waiting_time'][0]} min d'attente)."),
    },
    {
        "keywords": [r"occupation|occupancy|lits?\b|beds?"],
        "sql": """SELECT department_name, ROUND(AVG(occupancy_rate_pct), 1) AS occupancy_pct
                  FROM vw_daily_occupancy GROUP BY department_name ORDER BY occupancy_pct DESC""",
        "explain": lambda df, en: (
            f"{df['department_name'][0]} has the highest bed occupancy ({df['occupancy_pct'][0]} %)." if en else
            f"Le service le plus occupé est {df['department_name'][0]} ({df['occupancy_pct'][0]} % des lits en moyenne)."),
    },
    {
        "keywords": [r"personnel|staff|soignant", r"attente|attend|wait"],
        "sql": """SELECT staff_on_duty, ROUND(AVG(avg_waiting_time), 1) AS avg_wait, COUNT(*) AS days
                  FROM vw_staff_load WHERE department_name = 'Emergency'
                  GROUP BY staff_on_duty ORDER BY staff_on_duty""",
        "explain": lambda df, en: (
            f"In the ER, with {df['staff_on_duty'].iloc[0]} staff the wait is {df['avg_wait'].iloc[0]} min "
            f"vs {df['avg_wait'].iloc[-1]} min with {df['staff_on_duty'].iloc[-1]}." if en else
            f"Aux urgences, avec {df['staff_on_duty'].iloc[0]} soignants on attend {df['avg_wait'].iloc[0]} min, "
            f"contre {df['avg_wait'].iloc[-1]} min avec {df['staff_on_duty'].iloc[-1]} : moins de personnel = plus d'attente."),
    },
    {
        "keywords": [r"attente|attend|wait", r"service|department"],
        "sql": "SELECT department_name, avg_waiting_time FROM vw_department_kpis ORDER BY avg_waiting_time DESC",
        "explain": lambda df, en: (
            f"{df['department_name'][0]} has the longest average wait ({df['avg_waiting_time'][0]} min)." if en else
            f"Le service où l'on attend le plus est {df['department_name'][0]} ({df['avg_waiting_time'][0]} min en moyenne)."),
    },
    {
        "keywords": [r"attente|attend|wait"],
        "sql": "SELECT ROUND(AVG(waiting_time), 1) AS avg_waiting_time FROM fact_admission",
        "explain": lambda df, en: (
            f"The average waiting time is {df['avg_waiting_time'][0]} minutes." if en else
            f"Le temps d'attente moyen est de {df['avg_waiting_time'][0]} minutes."),
    },
    {
        "keywords": [r"s[ée]jour|stay"],
        "sql": "SELECT department_name, avg_length_of_stay FROM vw_department_kpis ORDER BY avg_length_of_stay DESC",
        "explain": lambda df, en: (
            f"Length of stay ranges from {df['avg_length_of_stay'].min()} to {df['avg_length_of_stay'].max()} days." if en else
            f"La durée moyenne de séjour va de {df['avg_length_of_stay'].min()} à {df['avg_length_of_stay'].max()} jours "
            f"selon le service ({df['department_name'][0]} la plus longue)."),
    },
    {
        "keywords": [r"co[uû]t|cost|pathologie|condition|factur|billing"],
        "sql": """SELECT medical_condition, ROUND(AVG(cost), 2) AS avg_cost FROM fact_admission
                  GROUP BY medical_condition ORDER BY avg_cost DESC""",
        "explain": lambda df, en: (
            f"{df['medical_condition'][0]} is the most expensive condition ({df['avg_cost'][0]:,.0f} on average)." if en else
            f"La pathologie la plus coûteuse est {df['medical_condition'][0]} ({df['avg_cost'][0]:,.0f} en moyenne)."),
    },
    {
        "keywords": [r"mois|month"],
        "sql": """SELECT d.year, d.month, COUNT(*) AS admissions FROM fact_admission f
                  JOIN dim_date d ON d.date_id = f.date_id GROUP BY d.year, d.month ORDER BY d.year, d.month""",
        "explain": lambda df, en: (
            f"About {df['admissions'].median():.0f} admissions per month (max {df['admissions'].max()})." if en else
            f"Environ {df['admissions'].median():.0f} admissions par mois (maximum {df['admissions'].max()})."),
    },
    {
        "keywords": [r"service|department"],
        "sql": "SELECT department_name, admissions FROM vw_department_kpis ORDER BY admissions DESC",
        "explain": lambda df, en: (
            f"{df['department_name'][0]} receives the most admissions ({df['admissions'][0]})." if en else
            f"Le service qui reçoit le plus d'admissions est {df['department_name'][0]} ({df['admissions'][0]})."),
    },
    {
        "keywords": [r"patient"],
        "sql": "SELECT COUNT(DISTINCT patient_id) AS patients FROM fact_admission",
        "explain": lambda df, en: (
            f"{df['patients'][0]} distinct patients were admitted." if en else
            f"{df['patients'][0]} patients différents ont été hospitalisés."),
    },
    {
        "keywords": [r"admission"],
        "sql": """SELECT COUNT(*) AS admissions,
                  ROUND(COUNT(*)::numeric / COUNT(DISTINCT admission_date), 1) AS per_day FROM fact_admission""",
        "explain": lambda df, en: (
            f"{df['admissions'][0]} admissions in total, {df['per_day'][0]} per day on average." if en else
            f"{df['admissions'][0]} admissions au total, soit {df['per_day'][0]} par jour en moyenne."),
    },
]


def match_template(question: str) -> dict | None:
    """Trouve le premier modèle dont tous les groupes de mots-clés apparaissent dans la question."""
    q = question.lower()
    for template in TEMPLATES:
        if all(re.search(pattern, q) for pattern in template["keywords"]):
            return template
    return None


# ======================= MODE LLM (si clé API) =======================

SCHEMA_DESCRIPTION = """PostgreSQL star schema of a hospital (data 2019-05-08 to 2024-05-07; "yesterday" = MAX(admission_date)).
fact_admission(admission_id, patient_id, date_id, department_id, staff_id, admission_date, discharge_date, hour,
  day_of_week 0=Monday, month, admission_type, medical_condition, patient_age, waiting_time minutes,
  length_of_stay days, cost, staff_on_duty, patients_per_staff, room_number, medication, test_result)
dim_patient(patient_id, full_name, gender, blood_type, birth_year, insurance_provider)
dim_date(date_id YYYYMMDD, full_date, year, quarter, month, month_name, day, day_of_week, day_name, is_weekend)
dim_department(department_id, department_name in Emergency/Cardiology/Oncology/Endocrinology/Pulmonology/Rheumatology,
  capacity_beds, daily_capacity)
dim_staff(staff_id, staff_name, role, department_id)
Views: vw_daily_kpis(admission_date, admissions, emergency_admissions, staff_on_duty, avg_waiting_time, hospital_daily_capacity),
vw_staff_load(admission_date, department_name, admissions, staff_on_duty, patients_per_staff, avg_waiting_time, daily_capacity),
vw_emergency_hourly(hour, admissions, avg_waiting_time), vw_department_kpis(department_name, admissions, avg_waiting_time,
avg_length_of_stay, avg_cost, avg_daily_admissions), vw_daily_occupancy(full_date, department_name, occupied_beds, occupancy_rate_pct),
vw_readmissions(patient_id, admission_id, admission_date, days_since_discharge), ml_daily_anomalies(full_date, admissions,
avg_waiting_time, staff_on_duty, anomaly_score, is_anomaly), ml_forecast(full_date, actual, predicted, is_next_day)."""


def llm_enabled() -> bool:
    """Le mode LLM est actif si un fournisseur est choisi (et sa clé fournie quand il en faut une)."""
    if LLM_PROVIDER == "ollama":
        return True                                  # local et gratuit : pas de clé
    if LLM_PROVIDER == "anthropic":
        return bool(ANTHROPIC_API_KEY)
    if LLM_PROVIDER == "openai":
        return bool(LLM_API_KEY and LLM_MODEL)
    return False


def post_json(url: str, body: dict, headers: dict, timeout: int = 120) -> dict:
    """Envoie une requête HTTP POST en JSON (bibliothèque standard, pas de dépendance en plus)."""
    request = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                     headers={"content-type": "application/json",
                                              "user-agent": "hospital-pipeline/1.0", **headers})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read())


def ask_llm(system: str, prompt: str) -> str:
    """Envoie une consigne et une question au LLM choisi, retourne sa réponse texte."""
    if LLM_PROVIDER == "anthropic":
        data = post_json("https://api.anthropic.com/v1/messages",
                         {"model": LLM_MODEL, "max_tokens": 800, "system": system,
                          "messages": [{"role": "user", "content": prompt}]},
                         {"x-api-key": ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01"}, timeout=60)
        return "".join(block.get("text", "") for block in data["content"]).strip()
    # Ollama et les API compatibles OpenAI (Groq...) utilisent le même format "chat/completions"
    headers = {"authorization": f"Bearer {LLM_API_KEY}"} if LLM_API_KEY else {}
    data = post_json(f"{LLM_BASE_URL.rstrip('/')}/chat/completions",
                     {"model": LLM_MODEL, "temperature": 0,
                      "messages": [{"role": "system", "content": system},
                                   {"role": "user", "content": prompt}]}, headers)
    return data["choices"][0]["message"]["content"].strip()


def extract_sql(text: str) -> str:
    """Récupère la requête dans la réponse du LLM (les petits modèles ajoutent parfois du texte)."""
    text = re.sub(r"```(?:sql)?", "", text, flags=re.IGNORECASE)
    match = re.search(r"\b(select|with)\b.*", text, flags=re.IGNORECASE | re.DOTALL)
    return (match.group(0) if match else text).strip().rstrip(";").strip()


def llm_answer(question: str) -> tuple[str, pd.DataFrame, str]:
    """Mode LLM : le modèle écrit le SQL, on le contrôle, on l'exécute, il explique le résultat."""
    sql = ask_llm(
        "You translate questions into ONE PostgreSQL SELECT query. Return ONLY the SQL, no markdown, "
        "no comments, no semicolon. Use only these tables:\n" + SCHEMA_DESCRIPTION, question)
    sql = extract_sql(sql)
    df = run_query(sql)
    explanation = ask_llm(
        "Answer in ONE short sentence, in the same language as the question, using only the data given.",
        f"Question: {question}\nSQL result:\n{df.head(20).to_csv(index=False)}")
    return sql, df, explanation


# ======================= POINT D'ENTRÉE =======================

def answer_with_mode(question: str, mode: str = "auto") -> tuple[str, pd.DataFrame, str, str]:
    """Comme answer(), mais indique aussi qui a répondu : "llm" ou "template" (utile pour l'interface)."""
    if mode in ("auto", "llm") and llm_enabled():
        try:
            return (*llm_answer(question), "llm")
        except Exception as exc:
            log.warning("Mode LLM indisponible (%s) -> mode modèles de questions", exc)
    template = match_template(question)
    if template is None:
        raise ValueError("Question non reconnue en mode sans LLM. Essayez une des questions d'exemple "
                         "ou activez un LLM dans .env (LLM_PROVIDER).")
    df = run_query(template["sql"])
    return template["sql"].strip(), df, template["explain"](df, is_english(question)), "template"


def answer(question: str, mode: str = "auto") -> tuple[str, pd.DataFrame, str]:
    """Répond à une question : retourne (SQL, résultat, explication en une phrase)."""
    sql, df, explanation, _ = answer_with_mode(question, mode)
    return sql, df, explanation


EXAMPLES = [
    "Combien de patients avons-nous pris en charge ?",
    "Quel service a le plus d'admissions ?",
    "What is the average waiting time by department?",
    "Quelles sont les heures de pointe des urgences ?",
    "Quel est le taux de réadmission ?",
    "Quelle est la durée moyenne de séjour ?",
    "Le manque de personnel augmente-t-il le temps d'attente ?",
    "Quels sont les jours anormaux ?",
    "Pourquoi le temps d'attente était élevé hier ?",
]


def print_answer(question: str, mode: str) -> None:
    """Affiche joliment la question, le SQL, le résultat et l'explication."""
    print(f"\n❓ {question}")
    try:
        sql, df, explanation = answer(question, mode)
    except Exception as exc:
        print(f"⛔ {exc}")
        return
    print("─── SQL généré " + "─" * 45)
    print(re.sub(r"\n\s*\n", "\n", sql))
    print("─── Résultat " + "─" * 47)
    print(df.head(10).to_string(index=False))
    print(f"💬 {explanation}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Agent IA : question -> SQL -> réponse")
    parser.add_argument("question", nargs="?", help="question en français ou en anglais")
    parser.add_argument("--examples", action="store_true", help="lance les questions d'exemple")
    parser.add_argument("--mode", choices=["auto", "template", "llm"], default="auto")
    args = parser.parse_args()
    use_llm = llm_enabled() and args.mode != "template"
    print(f"🤖 Agent SQL - mode : {f'LLM ({LLM_PROVIDER} / {LLM_MODEL})' if use_llm else 'modèles de questions (sans LLM)'}")

    if args.examples:
        for q in EXAMPLES:
            print_answer(q, args.mode)
    elif args.question:
        print_answer(args.question, args.mode)
    else:
        print("Posez une question (ligne vide pour quitter).")
        while question := input("\n> ").strip():
            print_answer(question, args.mode)


if __name__ == "__main__":
    main()
