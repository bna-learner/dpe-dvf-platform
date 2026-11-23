-- État courant des DPE selon la base complète : la photographie la plus récente.
CREATE OR REPLACE VIEW dpe_dvf_dev.silver_dpe_base_complete_courant AS
SELECT *
FROM dpe_dvf_dev.silver_dpe_base_complete
WHERE date_instantane = (
  SELECT max(date_instantane) FROM dpe_dvf_dev.silver_dpe_base_complete
)
