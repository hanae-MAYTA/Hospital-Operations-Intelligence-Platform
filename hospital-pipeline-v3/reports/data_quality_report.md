# Rapport de qualité des données

*Généré le 19/11/2026 à 18:34 — Hanae MAYTA & Wafae ZALOUK*

**Résultat : 28/28 contrôles réussis**

## Contrôles

| Statut | Contrôle | Critique | Détail |
|---|---|---|---|
| ✅ | Colonnes obligatoires (dim_patient) | oui | toutes présentes |
| ✅ | Colonnes obligatoires (dim_department) | oui | toutes présentes |
| ✅ | Colonnes obligatoires (dim_staff) | oui | toutes présentes |
| ✅ | Colonnes obligatoires (dim_date) | oui | toutes présentes |
| ✅ | Colonnes obligatoires (fact_admission) | oui | toutes présentes |
| ✅ | Table non vide (dim_patient) | oui | 48896 lignes |
| ✅ | Table non vide (dim_department) | oui | 6 lignes |
| ✅ | Table non vide (dim_staff) | oui | 79 lignes |
| ✅ | Table non vide (dim_date) | oui | 1827 lignes |
| ✅ | Table non vide (fact_admission) | oui | 50398 lignes |
| ✅ | Pas de doublons (dim_patient.patient_id) | oui | 0 doublon(s) |
| ✅ | Pas de doublons (dim_department.department_id) | oui | 0 doublon(s) |
| ✅ | Pas de doublons (dim_staff.staff_id) | oui | 0 doublon(s) |
| ✅ | Pas de doublons (dim_date.date_id) | oui | 0 doublon(s) |
| ✅ | Pas de doublons (fact_admission.admission_id) | oui | 0 doublon(s) |
| ✅ | Taux de valeurs manquantes | oui | pire colonne : 0.00% (seuil 5%) |
| ✅ | Pas de waiting_time négatif | oui | 0 valeur(s) négative(s) |
| ✅ | waiting_time < 24 h | non | 0 valeur(s) > 24 h |
| ✅ | Dates valides | oui | 0 date(s) illisible(s) |
| ✅ | Sortie après l'entrée | oui | 0 séjour(s) inversé(s) |
| ✅ | Pas de date dans le futur | non | 0 date(s) future(s) |
| ✅ | Clé étrangère patient_id -> dim_patient | oui | 0 orpheline(s) |
| ✅ | Clé étrangère date_id -> dim_date | oui | 0 orpheline(s) |
| ✅ | Clé étrangère department_id -> dim_department | oui | 0 orpheline(s) |
| ✅ | Clé étrangère staff_id -> dim_staff | oui | 0 orpheline(s) |
| ✅ | Coût positif | non | 0 négatif(s) |
| ✅ | Âge entre 0 et 110 | non | âges plausibles |
| ✅ | Durée de séjour >= 0 | non | durées positives |

## Nettoyage effectué (étape Transform)

| Opération | Nombre |
|---|---|
| rows_before | 56394 |
| duplicates_admission_id | 558 |
| dropped_unusable | 0 |
| duplicates_business | 5438 |
| dropped_unknown_patient | 0 |
| dates_inverted_fixed | 106 |
| waiting_time_impossible | 630 |
| billing_negative | 96 |
| age_impossible | 166 |
| staff_unknown | 666 |
| waiting_time_imputed | 2157 |
| billing_imputed | 1036 |
| age_imputed | 166 |
| hour_imputed | 495 |
| discharge_imputed | 287 |
| rows_after | 50398 |

## Volumes chargés

| Table | Lignes |
|---|---|
| dim_patient | 48896 |
| dim_department | 6 |
| dim_staff | 79 |
| dim_date | 1827 |
| fact_admission | 50398 |
