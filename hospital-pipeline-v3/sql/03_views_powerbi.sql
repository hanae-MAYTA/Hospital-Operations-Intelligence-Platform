-- =====================================================================
-- 03_views_powerbi.sql — Vues prêtes à l'emploi pour Power BI et l'agent IA
-- Hospital Operations Intelligence Platform — Hanae MAYTA & Wafae ZALOUK
-- "CREATE OR REPLACE VIEW" => relançable sans erreur.
-- =====================================================================

-- Vue détaillée : chaque admission avec les libellés des dimensions (table "à plat")
CREATE OR REPLACE VIEW vw_admissions_detail AS
SELECT f.admission_id, f.admission_date, f.discharge_date, d.year, d.month, d.month_name,
       d.day_name, d.is_weekend, f.hour, dep.department_name, f.admission_type,
       f.medical_condition, p.gender, p.insurance_provider, f.patient_age,
       s.role AS staff_role, f.waiting_time, f.length_of_stay, f.cost,
       f.staff_on_duty, f.patients_per_staff, f.test_result
FROM fact_admission f
JOIN dim_date d         ON d.date_id = f.date_id
JOIN dim_department dep ON dep.department_id = f.department_id
JOIN dim_patient p      ON p.patient_id = f.patient_id
JOIN dim_staff s        ON s.staff_id = f.staff_id;

-- Charge par jour et par service : volume, personnel, attente
CREATE OR REPLACE VIEW vw_staff_load AS
SELECT f.admission_date, dep.department_name,
       COUNT(*)                        AS admissions,
       MAX(f.staff_on_duty)            AS staff_on_duty,
       ROUND(COUNT(*)::numeric / NULLIF(MAX(f.staff_on_duty), 0), 2) AS patients_per_staff,
       ROUND(AVG(f.waiting_time), 1)   AS avg_waiting_time,
       dep.daily_capacity
FROM fact_admission f
JOIN dim_department dep ON dep.department_id = f.department_id
GROUP BY f.admission_date, dep.department_name, dep.daily_capacity;

-- Indicateurs quotidiens de tout l'hôpital
CREATE OR REPLACE VIEW vw_daily_kpis AS
SELECT admission_date,
       SUM(admissions)                                   AS admissions,
       SUM(admissions) FILTER (WHERE department_name = 'Emergency') AS emergency_admissions,
       SUM(staff_on_duty)                                AS staff_on_duty,
       ROUND(SUM(avg_waiting_time * admissions) / SUM(admissions), 1) AS avg_waiting_time,
       SUM(daily_capacity)                               AS hospital_daily_capacity
FROM vw_staff_load
GROUP BY admission_date;

-- Profil horaire des urgences (heures de pointe)
CREATE OR REPLACE VIEW vw_emergency_hourly AS
SELECT f.hour, COUNT(*) AS admissions, ROUND(AVG(f.waiting_time), 1) AS avg_waiting_time
FROM fact_admission f
JOIN dim_department dep ON dep.department_id = f.department_id
WHERE dep.department_name = 'Emergency'
GROUP BY f.hour;

-- Synthèse par service
CREATE OR REPLACE VIEW vw_department_kpis AS
SELECT dep.department_name, dep.capacity_beds, dep.daily_capacity,
       COUNT(*)                                AS admissions,
       ROUND(AVG(f.waiting_time), 1)           AS avg_waiting_time,
       ROUND(AVG(f.length_of_stay), 1)         AS avg_length_of_stay,
       ROUND(AVG(f.cost), 2)                   AS avg_cost,
       ROUND(COUNT(*)::numeric / COUNT(DISTINCT f.admission_date), 2) AS avg_daily_admissions
FROM fact_admission f
JOIN dim_department dep ON dep.department_id = f.department_id
GROUP BY dep.department_name, dep.capacity_beds, dep.daily_capacity;

-- Occupation des lits : un patient occupe un lit de son entrée (incluse) à sa sortie (exclue)
CREATE OR REPLACE VIEW vw_daily_occupancy AS
SELECT d.full_date, dep.department_name, dep.capacity_beds,
       COUNT(f.admission_id) AS occupied_beds,
       ROUND(100.0 * COUNT(f.admission_id) / dep.capacity_beds, 1) AS occupancy_rate_pct
FROM dim_date d
CROSS JOIN dim_department dep
LEFT JOIN fact_admission f
       ON f.department_id = dep.department_id
      AND d.full_date >= f.admission_date AND d.full_date < f.discharge_date
GROUP BY d.full_date, dep.department_name, dep.capacity_beds;

-- Réadmissions : nouvelle admission du même patient dans les 30 jours après sa sortie
CREATE OR REPLACE VIEW vw_readmissions AS
SELECT patient_id, admission_id, admission_date, previous_discharge,
       (admission_date - previous_discharge) AS days_since_discharge
FROM (
    SELECT patient_id, admission_id, admission_date,
           LAG(discharge_date) OVER (PARTITION BY patient_id ORDER BY admission_date) AS previous_discharge
    FROM fact_admission
) t
WHERE previous_discharge IS NOT NULL
  AND admission_date - previous_discharge BETWEEN 0 AND 30;
