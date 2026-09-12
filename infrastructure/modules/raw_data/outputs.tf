output "bucket_name" {
  value = aws_s3_bucket.raw_data.id
}

output "bucket_arn" {
  value = aws_s3_bucket.raw_data.arn
}
