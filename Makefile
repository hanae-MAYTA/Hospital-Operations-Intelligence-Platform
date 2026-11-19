# Hospital Operations Intelligence Platform — Hanae MAYTA & Wafae ZALOUK
# Raccourcis : `make all` lance toute la démo (après `make up`).
PY ?= python

.PHONY: help install up down data pipeline fail-demo app analytics kpis test ml agent ask all zip clean

help:      ## Affiche cette aide
	@grep -E '^[a-z-]+:.*##' Makefile | awk -F':.*## ' '{printf "  make %-10s %s\n", $$1, $$2}'

install:   ## Installe les dépendances Python
	$(PY) -m pip install -r requirements.txt

up:        ## Démarre PostgreSQL + Airflow (Docker)
	docker compose up -d

down:      ## Arrête les conteneurs
	docker compose down

data:      ## Génère les CSV sales dans data/raw/
	$(PY) scripts/generate_data.py

pipeline:  ## Lance Extract -> Transform -> Validate -> Load (sans Airflow)
	$(PY) -m src.pipeline

fail-demo: ## Démo : données invalides -> la pipeline s'arrête avant le chargement
	-$(PY) -m src.pipeline --simulate-bad-data

analytics: ## Exports Power BI + graphiques dans reports/
	$(PY) -m src.analytics

kpis:      ## Exécute les 15 requêtes KPI dans PostgreSQL
	docker compose exec -T postgres psql -U hospital -d hospital_dw < sql/02_kpis.sql

test:      ## Lance les tests pytest
	$(PY) -m pytest -v

ml:        ## Prévision des admissions + détection d'anomalies
	$(PY) -m src.ml.forecast
	$(PY) -m src.ml.anomaly

agent:     ## Lance l'agent IA sur les questions d'exemple
	$(PY) -m src.agent.sql_agent --examples

ask:       ## Pose une question à l'agent : make ask Q="Quel service attend le plus ?"
	$(PY) -m src.agent.sql_agent "$(Q)"

app:       ## Interface web : tableaux de bord + pipeline + assistant IA (http://localhost:8501)
	streamlit run dashboard/app.py

all: data pipeline analytics ml agent  ## Toute la démo d'un coup

zip:       ## Crée l'archive du projet
	cd .. && zip -rq hospital-pipeline.zip hospital-pipeline -x "*/venv/*" "*/.venv/*" "*/__pycache__/*" "*/.pytest_cache/*" "*/.env" "*/data/interim/*.pkl"

clean:     ## Supprime les fichiers générés
	rm -rf data/raw/*.csv data/processed/*.csv data/processed/powerbi data/interim/*.pkl reports/*.png reports/*.csv reports/*.json
