output "buckets" {
  description = "Nom du bucket de chaque couche."
  value       = { for couche, bucket in aws_s3_bucket.donnees : couche => bucket.bucket }
}
