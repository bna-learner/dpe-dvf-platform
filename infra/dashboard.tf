# Utilisateur IAM du dashboard (ADR-0003) : seule exception à la règle
# « aucune clé permanente ». Sa seule permission est la lecture du bucket gold.

resource "aws_iam_user" "dashboard" {
  name = "dpe-dvf-${var.environnement}-dashboard"
  path = "/applications/"
}

data "aws_iam_policy_document" "dashboard" {
  statement {
    sid       = "ListerGold"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.donnees["gold"].arn]
  }

  statement {
    sid       = "LireGold"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.donnees["gold"].arn}/*"]
  }
}

resource "aws_iam_user_policy" "dashboard" {
  name   = "lecture-gold"
  user   = aws_iam_user.dashboard.name
  policy = data.aws_iam_policy_document.dashboard.json
}

output "utilisateur_dashboard" {
  description = "Utilisateur IAM du dashboard, dont la clé est créée hors de Terraform."
  value       = aws_iam_user.dashboard.name
}
