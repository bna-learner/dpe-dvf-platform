-- Fraîcheur : nombre de jours depuis la dernière ingestion.
-- Au-delà de 8 jours, une exécution hebdomadaire a été manquée.
SELECT date_diff('day', max(date_ingestion), current_date) AS jours_depuis_derniere_ingestion
FROM dpe_dvf_dev.silver_dpe
