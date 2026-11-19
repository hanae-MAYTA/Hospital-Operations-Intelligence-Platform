# 🎤 Soutenance — Hospital Operations Intelligence Platform

**Hanae MAYTA & Wafae ZALOUK** — durée : 10 minutes + questions

---

## 1. Plan de la soutenance (10 min)

| Temps | Qui | Partie | Ce qu'il faut dire (idées clés) |
|---|---|---|---|
| 0:00 – 1:00 | **Hanae** | Introduction | Le problème : des données hospitalières incohérentes donnent des tableaux de bord faux. Notre objectif : une pipeline automatique qui garantit des données fiables, puis des usages (KPI, Power BI, ML, agent IA). |
| 1:00 – 2:30 | **Wafae** | Architecture et données | Schéma d'architecture. Analogie de la station de traitement de l'eau. Source : dataset Kaggle de 55 500 admissions, enrichi (service, heure, personnel, attente) puis volontairement sali. **Découverte : 5 438 doublons cachés dans Kaggle.** |
| 2:30 – 4:30 | **Hanae** | Les 4 étapes ETL | Extract (lecture sans modification), Transform (exemple AVANT/APRÈS : `Urgence`, `01/02/2024`, attente `-58` → Emergency, 2024-02-01, 47 min), Validate (28 contrôles, arrêt si critique), Load (upsert idempotent, une transaction). |
| 4:30 – 5:30 | **Wafae** | Schéma en étoile + Airflow | 1 table de faits + 4 dimensions, pourquoi ce modèle. DAG quotidien à 02:00, retries, même code avec ou sans Airflow. |
| 5:30 – 8:30 | **Wafae** puis **Hanae** | **Démo en direct** | Wafae : Airflow, logs, base, démo d'échec. Hanae : Power BI, agent IA (« Pourquoi l'attente était élevée hier ? »). |
| 8:30 – 9:30 | **Hanae** | ML et résultats | Prévision (MAE 4,60 contre 6,49 pour la baseline), Isolation Forest (19 jours anormaux), alerte de surcharge. Paradoxe de Simpson sur la corrélation personnel/attente. |
| 9:30 – 10:00 | **Wafae** | Conclusion | 34 tests verts, limites honnêtes (dataset synthétique), améliorations (incrémental, alertes, dbt/Great Expectations). |

> **Phrase d'ouverture (Hanae) :** « Si un même patient est compté deux fois et que les urgences
> s'appellent de trois façons différentes, le directeur de l'hôpital prend ses décisions sur des
> chiffres faux. Notre projet garantit que ça n'arrive pas, automatiquement, chaque nuit. »
>
> **Phrase de conclusion (Wafae) :** « La valeur du projet n'est pas le tableau de bord : c'est la
> confiance qu'on peut avoir dans chaque chiffre affiché, parce qu'il a passé 28 contrôles. »

---

## 2. Préparation (la veille et 15 min avant)

**La veille :** faire une répétition complète chronométrée, puis vérifier que le `.pbix` s'ouvre.

**15 minutes avant :**

```bash
docker compose up -d          # Airflow met 2 à 4 min à démarrer
make data && make pipeline && make analytics && make ml
```

Ouvrir à l'avance :
1. **Terminal 1** à la racine du projet (pour la démo).
2. **Navigateur** sur <http://localhost:8080> (connecté avec admin / admin), DAG activé.
3. **Power BI Desktop** avec le `.pbix`, sur la page *Executive Overview*.
4. **README.md** ouvert sur le schéma d'architecture (plan B visuel).
5. Un client SQL (DBeaver, pgAdmin ou `psql`) connecté à `hospital_dw`.

**Plan B si Docker ou Airflow ne démarre pas :** montrer `python -m src.pipeline` dans le terminal
(mêmes étapes, mêmes logs), les graphiques de `reports/`, et le README.

---

## 3. Scénario de démo en direct (3 min)

### Wafae — la pipeline (≈ 1 min 30)

1. **Airflow** → liste des DAGs : « Voici `hospital_etl_pipeline`, planifié tous les jours à 2 h. »
2. Cliquer sur le DAG → vue **Graph** → ▶ **Trigger DAG**.
   « Les 5 tâches s'enchaînent : chacune ne démarre que si la précédente a réussi. »
3. Pendant l'exécution (~30 s), cliquer sur **transform** → **Logs** :
   « 56 394 lignes en entrée, 50 398 en sortie : 558 doublons exacts, 5 438 doublons cachés… »
4. Cliquer sur **validate** → **Logs** : « 28 contrôles, tous ✅. »
5. Une fois tout vert, dans le client SQL :
   ```sql
   SELECT * FROM pipeline_runs ORDER BY run_id DESC LIMIT 3;
   SELECT COUNT(*) FROM fact_admission;   -- 50 398, même après plusieurs exécutions
   ```
   « Toujours 50 398 lignes : le chargement est idempotent. »
6. **Démo d'échec** dans le terminal :
   ```bash
   make fail-demo
   ```
   « J'injecte 3 temps d'attente négatifs : Validate les détecte, la pipeline s'arrête,
   l'échec est tracé dans `pipeline_runs`, et la base n'a pas bougé. »

### Hanae — les usages (≈ 1 min 30)

7. **Power BI** :
   - *Executive Overview* : les 5 cartes KPI ; cliquer sur le segment *Emergency*.
   - *Emergency Analytics* : « Les pics à 11 h et 19 h. »
   - *Staff & Capacity* : « Plus il y a de patients par soignant, plus l'attente monte. »
   - *Prediction & Alerts* : réel vs prédit, et les jours anormaux.
8. **Agent IA** dans le terminal :
   ```bash
   python -m src.agent.sql_agent "Quel service a le plus d'admissions ?"
   python -m src.agent.sql_agent "Pourquoi le temps d'attente était élevé hier ?"
   ```
   « L'agent a écrit le SQL, l'a exécuté en lecture seule, et explique : afflux de patients,
   sous-effectif aux urgences, jour anormal détecté par le modèle. »
9. *(si le temps le permet)* Montrer la sécurité :
   ```bash
   python -m pytest tests/test_agent.py -v
   ```
   « Un `DROP TABLE` ou un `DELETE` caché sont refusés. »

---

## 4. Les 15 questions probables du professeur

**1. Pourquoi ETL et pas ELT ?**
Les données hospitalières doivent être **contrôlées avant** d'entrer dans l'entrepôt : on ne veut
jamais qu'un rapport lise des données non validées. Notre volume (~56 000 lignes) tient en mémoire,
donc pandas suffit. L'ELT (charger le brut, puis transformer en SQL avec dbt) est préférable avec
de très gros volumes dans un entrepôt cloud puissant.

**2. Que se passe-t-il si les données sont invalides ?**
Validate lance 28 contrôles. Si un contrôle **critique** échoue, `ValidationError` est levée :
**rien n'est chargé**, l'échec est enregistré dans `pipeline_runs`, le rapport indique quelle
règle a échoué, et Airflow marque la tâche en rouge. *(Démo : `make fail-demo`.)*

**3. Comment évitez-vous les doublons au rechargement ?**
Par l'**upsert** : `INSERT … ON CONFLICT (clé primaire) DO UPDATE`. Une admission déjà présente
est mise à jour, jamais dupliquée. Testé : 2 chargements = toujours 50 398 lignes, et un test
pytest le vérifie automatiquement.

**4. Pourquoi un schéma en étoile ?**
Simple (une jointure par dimension), rapide pour les agrégations, recommandé par Power BI, et
sans répétition (le nom d'un service est stocké une fois). Les mesures sont dans la table de faits,
les axes d'analyse dans les dimensions.

**5. Comment automatiser ?**
Avec le DAG Airflow : tous les jours à 02:00, 5 tâches dépendantes, 2 nouvelles tentatives
en cas d'échec, logs et historique dans l'interface. Sans Airflow, une simple tâche cron
pourrait lancer `python -m src.pipeline`, mais sans interface ni retries par tâche.

**6. Comment avez-vous géré les valeurs manquantes ?**
Par la **médiane du service**, car les urgences attendent 49 min et l'oncologie 20 min : une
médiane globale fausserait les deux. La médiane résiste mieux que la moyenne aux valeurs extrêmes.
Une ligne sans date d'entrée lisible ou sans service reconnu est supprimée, car on ne peut pas la rattacher.

**7. Comment avez-vous trouvé les doublons cachés du dataset Kaggle ?**
Un `drop_duplicates()` classique ne les voyait pas, car l'âge et la casse du nom changent.
Nous avons défini une **clé métier** (patient, date d'entrée, date de sortie, pathologie,
chambre) : deux séjours identiques sur cette clé sont le même séjour.

**8. Pourquoi des fichiers intermédiaires entre les tâches Airflow ?**
Chaque tâche Airflow tourne dans un processus séparé. XCom est fait pour de petites valeurs,
pas pour des DataFrames de 50 000 lignes. Les tâches s'échangent donc des fichiers dans `data/interim/`.

**9. Votre modèle de prévision est-il vraiment utile ?**
Il réduit l'erreur de 29 % par rapport à « demain = aujourd'hui » (MAE 4,60 contre 6,49), et bat
légèrement la moyenne glissante. Le gain est modeste car le dataset Kaggle est synthétique, sans
saisonnalité. Nous l'avons évalué honnêtement : découpage **temporel** (la dernière année en test)
et lags calculés uniquement sur le passé, pour éviter toute fuite d'information.

**10. Pourquoi Isolation Forest ?**
Nous n'avons pas d'étiquettes « jour anormal » : il faut une méthode **non supervisée**. Elle
combine plusieurs variables (volume, attente, charge, personnel), là où un seuil fixe n'en regarde
qu'une. Elle retrouve les pics injectés, dont le 7 mai 2024.

**11. L'agent IA peut-il casser la base ?**
Non, il y a 5 protections : SELECT uniquement, mots-clés interdits, pas de commentaires, liste
blanche de tables, et exécution dans une transaction **READ ONLY** avec délai max et nombre de
lignes limité. 7 attaques sont testées dans `tests/test_agent.py`.

**12. Et si l'API du LLM ne répond pas ?**
L'agent bascule automatiquement en **mode sans clé** : 14 modèles de questions reconnus par
mots-clés, avec du SQL écrit et vérifié à l'avance. La démo fonctionne toujours.

**13. Comment savez-vous que votre code est correct ?**
Par 34 tests pytest : nettoyage (dates, services, doublons, valeurs impossibles), validation
(6 cas qui **doivent** échouer), un test de bout en bout avec chargement idempotent dans
PostgreSQL, et la sécurité de l'agent. Le DAG a aussi été exécuté en entier.

**14. Pourquoi la corrélation personnel/attente est-elle positive sur tout l'hôpital ?**
C'est le **paradoxe de Simpson** : les urgences ont à la fois le plus de personnel et le plus
d'attente. En la calculant **dans chaque service**, elle devient négative (−0,35 à −0,49) :
moins de personnel, plus d'attente.

**15. Que feriez-vous avec plus de temps ?**
Un chargement **incrémental** (seulement les nouvelles lignes), des alertes e-mail/Slack, des
contrôles industrialisés (Great Expectations ou dbt tests), un rôle PostgreSQL en lecture seule
pour l'agent et Power BI, une prévision par service et par heure, et une CI qui lance les tests à
chaque commit.

---

## 5. Questions bonus (si le professeur creuse)

- **Pourquoi Docker ?** Une commande lance PostgreSQL et Airflow avec les mêmes versions chez tout le monde.
- **Pourquoi PostgreSQL et pas SQLite ?** Vrai serveur multi-utilisateurs, fonctions analytiques (`LAG`, `CORR`, `PERCENTILE_CONT`), `ON CONFLICT`, connecteur natif Power BI.
- **Pourquoi une transaction unique au chargement ?** « Tout ou rien » : si la table de faits échoue, les dimensions ne restent pas à moitié mises à jour.
- **Pourquoi `dim_date` alors qu'on a déjà la date ?** Pour analyser facilement par jour de la semaine, mois, week-end, et pour les fonctions temporelles DAX (`DATEADD`).
- **C'est quoi `S000` ?** Un membre du personnel « Non renseigné » : on garde l'admission au lieu de la supprimer, et la clé étrangère reste valide.
