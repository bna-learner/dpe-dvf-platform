locals {
  couches = toset(["bronze", "silver", "gold", "athena-resultats"])
}

# Suffixe aléatoire : les noms de buckets doivent être uniques dans le monde entier.
resource "random_id" "suffixe" {
  byte_length = 3
}

resource "aws_s3_bucket" "donnees" {
  for_each = local.couches

  bucket        = "dpe-dvf-${var.environnement}-${each.key}-${random_id.suffixe.hex}"
  force_destroy = var.environnement == "dev"
}

resource "aws_s3_bucket_public_access_block" "donnees" {
  for_each = aws_s3_bucket.donnees

  bucket                  = each.value.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "donnees" {
  for_each = aws_s3_bucket.donnees

  bucket = each.value.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# Bronze est la source de vérité : on garde une trace des écrasements et suppressions.
resource "aws_s3_bucket_versioning" "bronze" {
  bucket = aws_s3_bucket.donnees["bronze"].id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "bronze" {
  bucket = aws_s3_bucket.donnees["bronze"].id

  rule {
    id     = "expirer-anciennes-versions"
    status = "Enabled"
    filter {}

    noncurrent_version_expiration {
      noncurrent_days = 30
    }
  }

  depends_on = [aws_s3_bucket_versioning.bronze]
}

resource "aws_s3_bucket_lifecycle_configuration" "athena_resultats" {
  bucket = aws_s3_bucket.donnees["athena-resultats"].id

  rule {
    id     = "expirer-resultats"
    status = "Enabled"
    filter {}

    expiration {
      days = 7
    }
  }
}
