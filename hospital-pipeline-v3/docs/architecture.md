# Architecture — Hospital Operations Intelligence Platform

*Hanae MAYTA & Wafae ZALOUK*

## 1. Vue d'ensemble (Mermaid)

> Ce schéma s'affiche automatiquement sur GitHub, GitLab et dans VS Code (extension Markdown Preview Mermaid).

```mermaid
flowchart LR
    K[(healthcare_dataset.csv<br/>Kaggle, 55 500 lignes)] --> G[scripts/generate_data.py<br/>enrichit + salit]
    G --> R[/data/raw/<br/>patients, admissions,<br/>departments, staff/]

    subgraph PIPE[Pipeline ETL — src/pipeline.py ou DAG Airflow 02:00]
        E[Extract] --> T[Transform] --> V{Validate}
        V -- ❌ contrôle critique --> STOP[Arrêt + log FAILED]
        V -- ✅ --> L[Load<br/>upsert]
        L --> Q[Quality check]
    end

    R --> E
    T --> P[/data/processed/<br/>CSV propres/]
    V --> REP[reports/data_quality_report.md]
    L --> DW[(PostgreSQL<br/>schéma en étoile)]

    DW --> SQL[sql/02_kpis.sql<br/>15 KPI]
    DW --> VW[sql/03_views_powerbi.sql<br/>vues]
    VW --> PBI[Power BI<br/>4 pages]
    DW --> ML[src/ml/<br/>prévision + anomalies]
    ML --> DW
    DW --> AG[src/agent/sql_agent.py<br/>question -> SQL -> réponse]
```

## 2. Vue d'ensemble (ASCII)

```
 healthcare_dataset.csv (Kaggle)
            │  scripts/generate_data.py  (enrichit : service, heure, attente, personnel
            ▼                             + salit : formats de dates, doublons, erreurs)
 data/raw/*.csv  ───────────────────────────────────────────────────────────────┐
                                                                                │
 ┌──────────────────────── PIPELINE (python -m src.pipeline / Airflow) ─────────▼────────┐
 │  EXTRACT ──► TRANSFORM ──► VALIDATE ──► LOAD ──► QUALITY CHECK                         │
 │  lit les CSV  nettoie,      28 contrôles  upsert dans   compte les lignes en base       │
 │               features      ✅/❌ ; stop    PostgreSQL    + 0 doublon                     │
 │                             si critique                                                │
 └────────────────────────────────┬───────────────────────────────────────────────────────┘
                                  ▼
                 ┌─────────── PostgreSQL : hospital_dw ───────────┐
                 │            dim_patient   dim_date               │
                 │                    ╲     ╱                      │
                 │                fact_admission                   │
                 │                    ╱     ╲                      │
                 │         dim_department   dim_staff              │
                 │  + pipeline_runs, ml_forecast, ml_daily_anomalies│
                 └──────┬──────────┬──────────┬──────────┬─────────┘
                        ▼          ▼          ▼          ▼
                   KPI SQL     Power BI     ML        Agent IA
```

## 3. Schéma en étoile

```mermaid
erDiagram
    fact_admission }o--|| dim_patient : "patient_id"
    fact_admission }o--|| dim_date : "date_id"
    fact_admission }o--|| dim_department : "department_id"
    fact_admission }o--|| dim_staff : "staff_id"
    dim_staff }o--o| dim_department : "department_id"

    fact_admission {
        varchar admission_id PK
        varchar patient_id FK
        int date_id FK
        int department_id FK
        varchar staff_id FK
        int waiting_time "minutes"
        int length_of_stay "jours"
        numeric cost
        int hour
        int staff_on_duty
        numeric patients_per_staff
    }
    dim_patient {
        varchar patient_id PK
        varchar full_name
        varchar gender
        varchar blood_type
        int birth_year
        varchar insurance_provider
    }
    dim_date {
        int date_id PK "AAAAMMJJ"
        date full_date
        int year
        int month
        varchar day_name
        bool is_weekend
    }
    dim_department {
        int department_id PK
        varchar department_name
        int capacity_beds
        int daily_capacity
    }
    dim_staff {
        varchar staff_id PK
        varchar staff_name
        varchar role
        int department_id FK
    }
```

## 4. Le DAG Airflow

```
hospital_etl_pipeline   (tous les jours à 02:00, 2 nouvelles tentatives, catchup désactivé)

  extract ──► transform ──► validate ──► load ──► quality_check
     │            │             │           │
     ▼            ▼             ▼           ▼
 interim/raw.pkl  interim/clean.pkl      PostgreSQL + pipeline_runs
                  data/processed/*.csv
                  reports/data_quality_report.md
```

Chaque tâche Airflow tourne dans un processus séparé : elles se transmettent les données
via des fichiers intermédiaires dans `data/interim/` (et non via XCom, réservé aux petites valeurs).
