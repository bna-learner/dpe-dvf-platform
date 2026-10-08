-- Pour chaque ingestion : retard maximal entre réception et ingestion parmi les DPE
-- vus pour la première fois. S'il approche 21 jours, la fenêtre est trop étroite.
WITH premiere_apparition AS (
  SELECT numero_dpe, min(date_ingestion) AS date_ingestion, min(date_reception_dpe) AS date_reception
  FROM dpe_dvf_dev.silver_dpe
  GROUP BY numero_dpe
)
SELECT
  date_ingestion,
  count(*) AS nb_nouveaux_dpe,
  max(date_diff('day', date_reception, date_ingestion)) AS retard_max_jours
FROM premiere_apparition
GROUP BY date_ingestion
ORDER BY date_ingestion;
