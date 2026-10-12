# Autorise les workflows GitHub Actions de la branche main à agir sur AWS,
# avec des identifiants temporaires obtenus par OIDC, sans aucune clé stockée.

locals {
  sujet_oidc_main = "repo:${var.github_proprietaire}@${var.github_proprietaire_id}/${var.github_depot}@${var.github_depot_id}:ref:refs/heads/main"
}

resource "aws_iam_openid_connect_provider" "github" {
  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]
}

# Politique de confiance : QUI peut endosser le rôle.
data "aws_iam_policy_document" "confiance_github" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github.arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values   = [local.sujet_oidc_main]
    }
  }
}

resource "aws_iam_role" "ingestion" {
  name                 = "dpe-dvf-${var.environnement}-ingestion"
  description          = "Endossé par GitHub Actions (branche main) pour l'ingestion des DPE."
  assume_role_policy   = data.aws_iam_policy_document.confiance_github.json
  max_session_duration = 21600 # 6 h : la durée maximale d'un job GitHub Actions
}

# Numéro de compte, récupéré dynamiquement : jamais écrit en dur.
data "aws_caller_identity" "courant" {}

# Politique de permissions : CE QUE le rôle peut faire.
data "aws_iam_policy_document" "ingestion" {
  statement {
    sid     = "ListerBronzeSilver"
    actions = ["s3:ListBucket"]
    resources = [
      aws_s3_bucket.donnees["bronze"].arn,
      aws_s3_bucket.donnees["silver"].arn,
    ]
  }

  statement {
    sid     = "LireEcrireBronzeSilver"
    actions = ["s3:GetObject", "s3:PutObject"]
    resources = [
      "${aws_s3_bucket.donnees["bronze"].arn}/*",
      "${aws_s3_bucket.donnees["silver"].arn}/*",
    ]
  }

  statement {
    sid       = "ExecuterRequetesAthena"
    actions   = ["athena:StartQueryExecution", "athena:GetQueryExecution", "athena:StopQueryExecution"]
    resources = [aws_athena_workgroup.dpe_dvf.arn]
  }

  statement {
    sid     = "LireCatalogueGlue"
    actions = ["glue:GetDatabase", "glue:GetTable", "glue:GetTables", "glue:GetPartitions"]
    resources = [
      "arn:aws:glue:${var.region}:${data.aws_caller_identity.courant.account_id}:catalog",
      aws_glue_catalog_database.dpe_dvf.arn,
      "arn:aws:glue:${var.region}:${data.aws_caller_identity.courant.account_id}:table/${aws_glue_catalog_database.dpe_dvf.name}/*",
    ]
  }

  statement {
    sid     = "LocaliserBuckets"
    actions = ["s3:GetBucketLocation"]
    resources = [
      aws_s3_bucket.donnees["silver"].arn,
      aws_s3_bucket.donnees["gold"].arn,
      aws_s3_bucket.donnees["athena-resultats"].arn,
    ]
  }

  statement {
    sid     = "ListerGoldEtResultats"
    actions = ["s3:ListBucket", "s3:ListBucketMultipartUploads"]
    resources = [
      aws_s3_bucket.donnees["gold"].arn,
      aws_s3_bucket.donnees["athena-resultats"].arn,
    ]
  }

  statement {
    sid = "EcrireGoldEtResultats"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
      "s3:AbortMultipartUpload",
      "s3:ListMultipartUploadParts",
    ]
    resources = [
      "${aws_s3_bucket.donnees["gold"].arn}/*",
      "${aws_s3_bucket.donnees["athena-resultats"].arn}/*",
    ]
  }
}

resource "aws_iam_role_policy" "ingestion" {
  name   = "acces-pipeline-donnees"
  role   = aws_iam_role.ingestion.id
  policy = data.aws_iam_policy_document.ingestion.json
}
