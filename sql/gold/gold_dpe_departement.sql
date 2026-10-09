-- Nombre de DPE par département, type de logement et étiquette énergie.
-- Règle métier : les DPE sans étiquette ou sans département sont exclus.
SELECT
  code_departement_ban AS code_departement,
  CASE dataset
    WHEN 'dpe03existant' THEN 'existant'
    WHEN 'dpe02neuf' THEN 'neuf'
  END AS type_logement,
  etiquette_dpe,
  count(*) AS nb_dpe
FROM dpe_dvf_dev.silver_dpe_courant
WHERE etiquette_dpe IS NOT NULL
  AND code_departement_ban IS NOT NULL
GROUP BY 1, 2, 3
ORDER BY 1, 2, 3
