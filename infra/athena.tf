# Catalogue Glue et groupe de travail Athena : interroger silver en SQL, sans crawler.

locals {
  # Doit rester aligné sur SCHEMA_SILVER (src/dpe_dvf/transformation/silver.py).
  colonnes_silver_dpe = [
    { nom = "numero_dpe", type = "string" },
    { nom = "date_etablissement_dpe", type = "date" },
    { nom = "date_reception_dpe", type = "date" },
    { nom = "date_derniere_modification_dpe", type = "date" },
    { nom = "etiquette_dpe", type = "string" },
    { nom = "etiquette_ges", type = "string" },
    { nom = "type_batiment", type = "string" },
    { nom = "periode_construction", type = "string" },
    { nom = "annee_construction", type = "int" },
    { nom = "surface_habitable_logement", type = "double" },
    { nom = "conso_5_usages_ep", type = "double" },
    { nom = "conso_5_usages_par_m2_ep", type = "double" },
    { nom = "identifiant_ban", type = "string" },
    { nom = "score_ban", type = "double" },
    { nom = "statut_geocodage", type = "string" },
    { nom = "adresse_brut", type = "string" },
    { nom = "nom_commune_brut", type = "string" },
    { nom = "code_postal_ban", type = "string" },
    { nom = "code_insee_ban", type = "string" },
    { nom = "code_departement_ban", type = "string" },
    { nom = "code_region_ban", type = "string" },
    { nom = "coordonnee_cartographique_x_ban", type = "double" },
    { nom = "coordonnee_cartographique_y_ban", type = "double" },
    { nom = "dataset", type = "string" },
    { nom = "date_ingestion", type = "date" },
  ]
}

resource "aws_glue_catalog_database" "dpe_dvf" {
  name        = "dpe_dvf_${var.environnement}"
  description = "Tables de la plateforme DPE et DVF."
}

resource "aws_glue_catalog_table" "silver_dpe" {
  database_name = aws_glue_catalog_database.dpe_dvf.name
  name          = "silver_dpe"
  description   = "DPE validés et typés (couche silver), un fichier Parquet par lot bronze."
  table_type    = "EXTERNAL_TABLE"

  parameters = {
    EXTERNAL       = "TRUE"
    classification = "parquet"
  }

  storage_descriptor {
    location      = "s3://${aws_s3_bucket.donnees["silver"].bucket}/dpe/"
    input_format  = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat"

    ser_de_info {
      serialization_library = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
    }

    dynamic "columns" {
      for_each = local.colonnes_silver_dpe
      content {
        name = columns.value.nom
        type = columns.value.type
      }
    }
  }
}

resource "aws_athena_workgroup" "dpe_dvf" {
  name          = "dpe-dvf-${var.environnement}"
  description   = "Requêtes de la plateforme DPE et DVF."
  force_destroy = var.environnement == "dev"

  configuration {
    enforce_workgroup_configuration    = true
    publish_cloudwatch_metrics_enabled = true
    bytes_scanned_cutoff_per_query     = 1073741824 # 1 Go : garde-fou contre une requête trop coûteuse

    result_configuration {
      output_location = "s3://${aws_s3_bucket.donnees["athena-resultats"].bucket}/resultats/"

      encryption_configuration {
        encryption_option = "SSE_S3"
      }
    }
  }
}
