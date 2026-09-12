# Private bucket for data-pipeline's collected raw data (and whatever other
# program later maintains it). No web access, no CORS — this isn't served
# to a browser like the frontend bucket.

data "aws_caller_identity" "current" {}

resource "aws_s3_bucket" "raw_data" {
  bucket = "${var.project_name}-raw-data-${data.aws_caller_identity.current.account_id}"

  tags = {
    Project     = var.project_name
    Environment = var.environment
  }
}

resource "aws_s3_bucket_ownership_controls" "raw_data" {
  bucket = aws_s3_bucket.raw_data.id
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_public_access_block" "raw_data" {
  bucket                  = aws_s3_bucket.raw_data.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "raw_data" {
  bucket = aws_s3_bucket.raw_data.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "raw_data" {
  bucket = aws_s3_bucket.raw_data.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# Versioning without cleanup grows forever once something writes to this
# bucket regularly; expire old versions rather than keeping every overwrite.
resource "aws_s3_bucket_lifecycle_configuration" "raw_data" {
  bucket = aws_s3_bucket.raw_data.id
  rule {
    id     = "expire-noncurrent-versions"
    status = "Enabled"
    noncurrent_version_expiration {
      noncurrent_days = 90
    }
  }
}
