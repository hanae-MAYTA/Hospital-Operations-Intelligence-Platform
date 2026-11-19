-- =====================================================================
-- 02_kpis.sql — 14 indicateurs clés (KPI) sur le Data Warehouse
-- Hospital Operations Intelligence Platform — Hanae MAYTA & Wafae ZALOUK
-- Chaque requête commence par la QUESTION BUSINESS à laquelle elle répond.
-- Lancer : psql -h localhost -U hospital -d hospital_dw -f sql/02_kpis.sql
-- =====================================================================

-- KPI 1 — Combien de patients différents avons-nous pris en charge ?
SELECT COUNT(DISTINCT patient_id) AS nb_patients FROM fact_admission;

-- KPI 2 — Combien d'admissions au total, et en moyenne par jour ?
SELECT COUNT(*) AS nb_admissions,
       ROUND(COUNT(*)::numeric / COUNT(DISTINCT admission_date), 1) AS admissions_par_jour
FROM fact_admission;

-- KPI 3 — Combien de temps un patient attend-il en moyenne (et en médiane) ?
SELECT ROUND(AVG(waiting_time), 1) AS attente_moyenne_min,
       PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY waiting_time) AS attente_mediane_min
FROM fact_admission;

-- KPI 4 — Quel service fait attendre le plus ses patients ?
SELECT dep.department_name, ROUND(AVG(f.waiting_time), 1) AS attente_moyenne_min
FROM fact_admission f JOIN dim_department dep USING (department_id)
GROUP BY dep.department_name ORDER BY attente_moyenne_min DESC;

-- KPI 5 — Combien de jours un patient reste-t-il hospitalisé, par service ?
SELECT dep.department_name, ROUND(AVG(f.length_of_stay), 1) AS duree_sejour_moyenne_jours
FROM fact_admission f JOIN dim_department dep USING (department_id)
GROUP BY dep.department_name ORDER BY duree_sejour_moyenne_jours DESC;

-- KPI 6 — Nos lits sont-ils saturés ? (taux d'occupation moyen par service)
SELECT department_name, ROUND(AVG(occupancy_rate_pct), 1) AS taux_occupation_moyen_pct,
       MAX(occupancy_rate_pct) AS taux_occupation_max_pct
FROM vw_daily_occupancy
GROUP BY department_name ORDER BY taux_occupation_moyen_pct DESC;

-- KPI 7 — Quelle part des patients revient dans les 30 jours ? (taux de réadmission)
SELECT (SELECT COUNT(*) FROM vw_readmissions) AS readmissions_30j,
       ROUND(100.0 * (SELECT COUNT(*) FROM vw_readmissions) / COUNT(*), 2) AS taux_readmission_pct
FROM fact_admission;

-- KPI 8 — Quels services reçoivent le plus d'admissions ?
SELECT dep.department_name, COUNT(*) AS admissions,
       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1) AS part_pct
FROM fact_admission f JOIN dim_department dep USING (department_id)
GROUP BY dep.department_name ORDER BY admissions DESC;

-- KPI 9 — Quels jours de la semaine sont les plus chargés ?
SELECT d.day_of_week, d.day_name, COUNT(*) AS admissions
FROM fact_admission f JOIN dim_date d USING (date_id)
GROUP BY d.day_of_week, d.day_name ORDER BY d.day_of_week;

-- KPI 10 — Comment évoluent les admissions mois par mois ?
SELECT d.year, d.month, d.month_name, COUNT(*) AS admissions,
       ROUND(AVG(f.waiting_time), 1) AS attente_moyenne_min
FROM fact_admission f JOIN dim_date d USING (date_id)
GROUP BY d.year, d.month, d.month_name ORDER BY d.year, d.month;

-- KPI 11 — À quelles heures les urgences sont-elles saturées ? (heures de pointe)
SELECT hour, admissions, avg_waiting_time
FROM vw_emergency_hourly ORDER BY admissions DESC LIMIT 5;

-- KPI 12 — Moins de personnel = plus d'attente ? (corrélation calculée DANS chaque service,
--          car comparer les urgences à la rhumatologie fausserait le résultat)
SELECT department_name,
       ROUND(CORR(staff_on_duty, avg_waiting_time)::numeric, 3)      AS correlation_personnel_attente,
       ROUND(CORR(patients_per_staff, avg_waiting_time)::numeric, 3) AS correlation_charge_attente
FROM vw_staff_load
GROUP BY department_name ORDER BY correlation_personnel_attente;

-- KPI 12 bis — Même question, en tranches lisibles pour la direction
SELECT CASE WHEN patients_per_staff < 1 THEN '1. < 1 patient/soignant'
            WHEN patients_per_staff < 2 THEN '2. 1 à 2'
            WHEN patients_per_staff < 4 THEN '3. 2 à 4'
            ELSE '4. 4 et plus' END            AS charge,
       COUNT(*)                                AS jours_service,
       ROUND(AVG(avg_waiting_time), 1)         AS attente_moyenne_min
FROM vw_staff_load GROUP BY 1 ORDER BY 1;

-- KPI 13 — Combien coûte une hospitalisation selon la pathologie ?
SELECT medical_condition, ROUND(AVG(cost), 2) AS cout_moyen, ROUND(SUM(cost), 0) AS cout_total
FROM fact_admission GROUP BY medical_condition ORDER BY cout_moyen DESC;

-- KPI 14 — Combien de jours avons-nous dépassé la capacité d'accueil quotidienne ?
SELECT department_name, COUNT(*) AS jours_en_depassement
FROM vw_staff_load WHERE admissions > daily_capacity
GROUP BY department_name ORDER BY jours_en_depassement DESC;
