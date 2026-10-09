-- Performance énergétique selon la période de construction.
-- Médianes plutôt que moyennes : robustes aux valeurs aberrantes des saisies brutes.
SELECT
  periode_construction,
  CASE dataset
    WHEN 'dpe03existant' THEN 'existant'
    WHEN 'dpe02neuf' THEN 'neuf'
  END AS type_logement,
  count(*) AS nb_dpe,
  approx_percentile(conso_5_usages_par_m2_ep, 0.5) AS conso_ep_m2_mediane,
  approx_percentile(surface_habitable_logement, 0.5) AS surface_mediane_m2,
  avg(CASE WHEN etiquette_dpe IN ('F', 'G') THEN 1.0 ELSE 0.0 END) AS part_passoires
FROM dpe_dvf_dev.silver_dpe_courant
WHERE etiquette_dpe IS NOT NULL
  AND periode_construction IS NOT NULL
GROUP BY 1, 2
ORDER BY 1, 2
