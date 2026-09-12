output "bucket_name" {
  value = aws_s3_bucket.transformed_data.id
}

output "bucket_arn" {
  value = aws_s3_bucket.transformed_data.arn
}
