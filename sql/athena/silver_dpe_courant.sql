-- Une ligne par DPE : la version la plus récemment modifiée, puis la plus récemment ingérée.
CREATE OR REPLACE VIEW dpe_dvf_dev.silver_dpe_courant AS
SELECT *
FROM (
  SELECT
    *,
    row_number() OVER (
      PARTITION BY numero_dpe
      ORDER BY date_derniere_modification_dpe DESC NULLS LAST, date_ingestion DESC
    ) AS rang
  FROM dpe_dvf_dev.silver_dpe
)
WHERE rang = 1;
