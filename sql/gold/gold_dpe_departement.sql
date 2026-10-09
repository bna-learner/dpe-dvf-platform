-- Nombre de DPE par département, type de logement et étiquette énergie.
-- Département : celui de la BAN, sinon celui déduit du code postal saisi (voir source_departement).
-- Règle métier : les DPE sans étiquette ou sans département sont exclus.
SELECT
  code_departement,
  CASE dataset
    WHEN 'dpe03existant' THEN 'existant'
    WHEN 'dpe02neuf' THEN 'neuf'
  END AS type_logement,
  etiquette_dpe,
  count(*) AS nb_dpe,
  count_if(source_departement = 'code_postal') AS nb_dpe_departement_deduit
FROM dpe_dvf_dev.silver_dpe_courant
WHERE etiquette_dpe IS NOT NULL
  AND code_departement IS NOT NULL
GROUP BY 1, 2, 3
ORDER BY 1, 2, 3
