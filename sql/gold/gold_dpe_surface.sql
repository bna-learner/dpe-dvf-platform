-- Part de passoires (F et G) selon la surface et le type de bâtiment, logements existants.
-- Mesure l'effet de la surface sur l'étiquette (biais connu des petites surfaces).
SELECT
  CASE
    WHEN surface_habitable_logement < 20 THEN '1. moins de 20 m²'
    WHEN surface_habitable_logement < 40 THEN '2. de 20 à 40 m²'
    WHEN surface_habitable_logement < 70 THEN '3. de 40 à 70 m²'
    WHEN surface_habitable_logement < 100 THEN '4. de 70 à 100 m²'
    ELSE '5. 100 m² et plus'
  END AS tranche_surface,
  type_batiment,
  count(*) AS nb_dpe,
  avg(CASE WHEN etiquette_dpe IN ('F', 'G') THEN 1.0 ELSE 0.0 END) AS part_passoires
FROM dpe_dvf_dev.silver_dpe_courant
WHERE dataset = 'dpe03existant'
  AND etiquette_dpe IS NOT NULL
  AND surface_habitable_logement IS NOT NULL
GROUP BY 1, 2
ORDER BY 1, 2
