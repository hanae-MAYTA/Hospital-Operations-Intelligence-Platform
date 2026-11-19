"""
Tests de l'agent SQL : la sécurité (SELECT seulement, liste blanche) et la reconnaissance
des questions en mode sans clé. Aucun accès à la base n'est nécessaire.
Auteures : Hanae MAYTA et Wafae ZALOUK
"""
import pytest

from src.agent.sql_agent import EXAMPLES, is_safe_sql, match_template


@pytest.mark.parametrize("sql", [
    "SELECT COUNT(*) FROM fact_admission",
    "WITH t AS (SELECT * FROM vw_daily_kpis) SELECT * FROM t",
    "select d.year from fact_admission f join dim_date d on d.date_id = f.date_id;",
])
def test_safe_queries_accepted(sql):
    assert is_safe_sql(sql)[0]


@pytest.mark.parametrize("sql, reason", [
    ("DROP TABLE fact_admission", "SELECT"),
    ("DELETE FROM fact_admission", "SELECT"),
    ("SELECT 1; DROP TABLE dim_patient", "une seule"),
    ("SELECT * FROM pg_user", "non autorisée"),
    ("SELECT * FROM fact_admission -- commentaire", "commentaires"),
    ("WITH x AS (DELETE FROM dim_staff RETURNING *) SELECT * FROM x", "DELETE"),
    ("SELECT * INTO copie FROM fact_admission", "INTO"),
])
def test_dangerous_queries_refused(sql, reason):
    safe, message = is_safe_sql(sql)
    assert not safe and reason in message


def test_all_examples_are_recognized():
    for question in EXAMPLES:
        assert match_template(question) is not None, question


def test_why_question_uses_comparison_template():
    template = match_template("Pourquoi le temps d'attente était élevé hier ?")
    assert "ml_daily_anomalies" in template["sql"]


def test_extract_sql_from_chatty_llm_answer():
    from src.agent.sql_agent import extract_sql
    text = "Voici la requête :\n```sql\nSELECT COUNT(*) FROM fact_admission;\n```"
    assert extract_sql(text) == "SELECT COUNT(*) FROM fact_admission"
