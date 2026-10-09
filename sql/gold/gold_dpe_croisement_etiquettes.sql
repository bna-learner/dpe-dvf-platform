-- Croisement des étiquettes énergie et GES : révèle les logements déclassés
-- par leurs émissions plutôt que par leur consommation (double seuil).
SELECT
  etiquette_dpe,
  etiquette_ges,
  CASE dataset
    WHEN 'dpe03existant' THEN 'existant'
    WHEN 'dpe02neuf' THEN 'neuf'
  END AS type_logement,
  count(*) AS nb_dpe
FROM dpe_dvf_dev.silver_dpe_courant
WHERE etiquette_dpe IS NOT NULL
  AND etiquette_ges IS NOT NULL
GROUP BY 1, 2, 3
ORDER BY 1, 2, 3
