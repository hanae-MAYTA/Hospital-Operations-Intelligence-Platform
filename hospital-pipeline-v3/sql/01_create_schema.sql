-- =====================================================================
-- 01_create_schema.sql — Data Warehouse en schéma en étoile
-- Hospital Operations Intelligence Platform — Hanae MAYTA & Wafae ZALOUK
--
-- Au centre : fact_admission (1 ligne = 1 admission, avec les mesures)
-- Autour    : les dimensions (qui ? quand ? où ? par qui ?)
-- "IF NOT EXISTS" => le script peut être relancé sans erreur (idempotent).
-- =====================================================================

-- QUI ? Le patient
CREATE TABLE IF NOT EXISTS dim_patient (
    patient_id          VARCHAR(10) PRIMARY KEY,
    full_name           VARCHAR(100) NOT NULL,
    gender              VARCHAR(10)  NOT NULL,
    blood_type          VARCHAR(5),
    birth_year          INTEGER,
    insurance_provider  VARCHAR(50)
);

-- QUAND ? Le calendrier (une ligne par jour)
CREATE TABLE IF NOT EXISTS dim_date (
    date_id      INTEGER PRIMARY KEY,          -- format AAAAMMJJ, ex : 20240507
    full_date    DATE NOT NULL UNIQUE,
    year         INTEGER NOT NULL,
    quarter      INTEGER NOT NULL,
    month        INTEGER NOT NULL,
    month_name   VARCHAR(15) NOT NULL,
    day          INTEGER NOT NULL,
    day_of_week  INTEGER NOT NULL,             -- 0 = lundi ... 6 = dimanche
    day_name     VARCHAR(10) NOT NULL,
    is_weekend   BOOLEAN NOT NULL
);

-- OÙ ? Le service hospitalier
CREATE TABLE IF NOT EXISTS dim_department (
    department_id    INTEGER PRIMARY KEY,
    department_name  VARCHAR(50) NOT NULL UNIQUE,
    capacity_beds    INTEGER NOT NULL,
    daily_capacity   INTEGER NOT NULL          -- admissions/jour absorbables
);

-- PAR QUI ? Le personnel soignant
CREATE TABLE IF NOT EXISTS dim_staff (
    staff_id       VARCHAR(10) PRIMARY KEY,
    staff_name     VARCHAR(100) NOT NULL,
    role           VARCHAR(20) NOT NULL,
    department_id  INTEGER REFERENCES dim_department(department_id)
);

-- LE FAIT : une admission et ses mesures
CREATE TABLE IF NOT EXISTS fact_admission (
    admission_id        VARCHAR(10) PRIMARY KEY,
    patient_id          VARCHAR(10) NOT NULL REFERENCES dim_patient(patient_id),
    date_id             INTEGER     NOT NULL REFERENCES dim_date(date_id),
    department_id       INTEGER     NOT NULL REFERENCES dim_department(department_id),
    staff_id            VARCHAR(10) NOT NULL REFERENCES dim_staff(staff_id),
    admission_date      DATE NOT NULL,
    discharge_date      DATE NOT NULL,
    hour                INTEGER CHECK (hour BETWEEN 0 AND 23),
    day_of_week         INTEGER,
    month               INTEGER,
    admission_type      VARCHAR(20),
    medical_condition   VARCHAR(30),
    patient_age         INTEGER,
    waiting_time        INTEGER NOT NULL CHECK (waiting_time >= 0),   -- minutes
    length_of_stay      INTEGER NOT NULL CHECK (length_of_stay >= 0), -- jours
    cost                NUMERIC(12, 2) NOT NULL,
    staff_on_duty       INTEGER,
    patients_per_staff  NUMERIC(6, 2),
    room_number         INTEGER,
    medication          VARCHAR(30),
    test_result         VARCHAR(20)
);

CREATE INDEX IF NOT EXISTS idx_fact_date       ON fact_admission(date_id);
CREATE INDEX IF NOT EXISTS idx_fact_department ON fact_admission(department_id);
CREATE INDEX IF NOT EXISTS idx_fact_patient    ON fact_admission(patient_id);

-- Historique des exécutions de la pipeline (traçabilité)
CREATE TABLE IF NOT EXISTS pipeline_runs (
    run_id            SERIAL PRIMARY KEY,
    run_date          TIMESTAMP NOT NULL DEFAULT NOW(),
    status            VARCHAR(10) NOT NULL,      -- SUCCESS / FAILED
    rows_loaded       INTEGER,
    duration_seconds  NUMERIC(8, 2),
    message           TEXT
);

-- Résultats de la détection d'anomalies (écrits par src/ml/anomaly.py)
CREATE TABLE IF NOT EXISTS ml_daily_anomalies (
    full_date               DATE PRIMARY KEY,
    admissions              INTEGER,
    avg_waiting_time        NUMERIC(8, 2),
    avg_patients_per_staff  NUMERIC(6, 2),
    staff_on_duty           INTEGER,
    anomaly_score           NUMERIC(8, 4),
    is_anomaly              BOOLEAN
);

-- Prévisions des admissions (écrites par src/ml/forecast.py) : test + prévision du lendemain
CREATE TABLE IF NOT EXISTS ml_forecast (
    full_date    DATE PRIMARY KEY,
    actual       INTEGER,                    -- vide pour le jour prévu (futur)
    predicted    NUMERIC(8, 2),
    is_next_day  BOOLEAN NOT NULL DEFAULT FALSE
);
