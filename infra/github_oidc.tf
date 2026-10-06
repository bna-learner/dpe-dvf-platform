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
}

resource "aws_iam_role_policy" "ingestion" {
  name   = "acces-bronze-silver"
  role   = aws_iam_role.ingestion.id
  policy = data.aws_iam_policy_document.ingestion.json
}
