-- Exécuté une seule fois à la création du conteneur PostgreSQL :
-- crée une base séparée pour les métadonnées d'Airflow (la base hospital_dw reste propre).
CREATE DATABASE airflow OWNER hospital;
