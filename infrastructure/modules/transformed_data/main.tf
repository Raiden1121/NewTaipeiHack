# Private bucket for data-pipeline's raw-data-transformed output. Nothing
# else reads or writes into it yet — access wiring (IAM for whatever job
# maintains this bucket) comes later once that integration actually happens.

data "aws_caller_identity" "current" {}

resource "aws_s3_bucket" "transformed_data" {
  bucket = "${var.project_name}-transformed-data-${data.aws_caller_identity.current.account_id}"

  tags = {
    Project     = var.project_name
    Environment = var.environment
  }
}

resource "aws_s3_bucket_ownership_controls" "transformed_data" {
  bucket = aws_s3_bucket.transformed_data.id
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_public_access_block" "transformed_data" {
  bucket                  = aws_s3_bucket.transformed_data.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "transformed_data" {
  bucket = aws_s3_bucket.transformed_data.id
  versioning_configuration {
    status = "Enabled"
  }
}
