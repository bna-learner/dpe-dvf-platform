-- Consommation d'énergie primaire par étiquette énergie, logements existants et neufs.
-- Moyenne et médiane : leur écart révèle les valeurs extrêmes des saisies brutes.
SELECT
  etiquette_dpe,
  CASE dataset
    WHEN 'dpe03existant' THEN 'existant'
    WHEN 'dpe02neuf' THEN 'neuf'
  END AS type_logement,
  count(*) AS nb_dpe,
  avg(conso_5_usages_par_m2_ep) AS conso_ep_m2_moyenne,
  approx_percentile(conso_5_usages_par_m2_ep, 0.5) AS conso_ep_m2_mediane
FROM dpe_dvf_dev.silver_dpe_courant
WHERE etiquette_dpe IS NOT NULL
  AND conso_5_usages_par_m2_ep IS NOT NULL
GROUP BY 1, 2
ORDER BY 1, 2
