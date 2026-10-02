# Crée le bucket qui héberge le state Terraform de tout le projet.
# Configuration à part : le bucket doit exister avant de pouvoir y stocker un state.

terraform {
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
}

provider "aws" {
  region = "eu-west-3"

  default_tags {
    tags = {
      projet    = "dpe-dvf-platform"
      composant = "bootstrap"
      gere_par  = "terraform"
    }
  }
}

resource "random_id" "suffixe" {
  byte_length = 3
}

resource "aws_s3_bucket" "tfstate" {
  bucket = "dpe-dvf-tfstate-${random_id.suffixe.hex}"

  # Ce bucket contient la mémoire de Terraform : on interdit sa destruction.
  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_versioning" "tfstate" {
  bucket = aws_s3_bucket.tfstate.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "tfstate" {
  bucket = aws_s3_bucket.tfstate.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "tfstate" {
  bucket                  = aws_s3_bucket.tfstate.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "tfstate" {
  bucket = aws_s3_bucket.tfstate.id

  rule {
    id     = "expirer-anciennes-versions"
    status = "Enabled"
    filter {}

    noncurrent_version_expiration {
      noncurrent_days = 90
    }
  }

  depends_on = [aws_s3_bucket_versioning.tfstate]
}

output "bucket_state" {
  description = "Nom du bucket qui héberge le state Terraform."
  value       = aws_s3_bucket.tfstate.bucket
}
