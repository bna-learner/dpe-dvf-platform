output "buckets" {
  description = "Nom du bucket de chaque couche."
  value       = { for couche, bucket in aws_s3_bucket.donnees : couche => bucket.bucket }
}

output "role_ingestion_arn" {
  description = "ARN du rôle endossé par le workflow d'ingestion."
  value       = aws_iam_role.ingestion.arn
}
