data "aws_caller_identity" "current" {}

data "aws_cloudfront_cache_policy" "caching_optimized" {
  name = "Managed-CachingOptimized"
}

data "aws_cloudfront_cache_policy" "caching_disabled" {
  name = "Managed-CachingDisabled"
}

data "aws_cloudfront_origin_request_policy" "all_viewer_except_host" {
  name = "Managed-AllViewerExceptHostHeader"
}

locals {
  ai_origin_id = "ai-service-function-url"
  # https://abc.lambda-url.<region>.on.aws/ -> abc.lambda-url.<region>.on.aws
  ai_origin_domain = trimsuffix(trimprefix(var.ai_function_url, "https://"), "/")
}

# --- S3: private bucket holding the built frontend assets (frontend/dist) ---

resource "aws_s3_bucket" "frontend" {
  bucket = "${var.project_name}-frontend-${data.aws_caller_identity.current.account_id}"

  tags = {
    Project     = var.project_name
    Environment = var.environment
  }
}

resource "aws_s3_bucket_ownership_controls" "frontend" {
  bucket = aws_s3_bucket.frontend.id
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_public_access_block" "frontend" {
  bucket                  = aws_s3_bucket.frontend.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# --- CloudFront: serves the bucket via Origin Access Control, SPA fallback ---

resource "aws_cloudfront_origin_access_control" "frontend" {
  name                              = "${var.project_name}-frontend-oac"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

# Signs /api/ai requests to the AI Service's AWS_IAM Function URL. Viewers must
# send `x-amz-content-sha256` (hex SHA-256 of the body) on POST, because
# CloudFront does not hash request bodies itself; frontend/src/lib/api/ai.ts
# does this.
resource "aws_cloudfront_origin_access_control" "ai_service" {
  count = var.enable_ai_origin ? 1 : 0

  name                              = "${var.project_name}-ai-service-oac"
  origin_access_control_origin_type = "lambda"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

# S3 (via OAC/REST API, not the S3 website endpoint) doesn't auto-resolve a
# directory request to its index.html, so /slides or /slides/ would otherwise
# 403 -> fall back to the React SPA's index.html instead of the slide deck.
resource "aws_cloudfront_function" "slides_index" {
  name    = "${var.project_name}-slides-index-rewrite"
  runtime = "cloudfront-js-1.0"
  comment = "Rewrite /slides and /slides/ to /slides/index.html"
  publish = true
  code    = <<-EOT
    function handler(event) {
      var request = event.request;
      if (request.uri === "/slides" || request.uri === "/slides/") {
        request.uri = "/slides/index.html";
      }
      return request;
    }
  EOT
}

resource "aws_cloudfront_distribution" "frontend" {
  enabled             = true
  default_root_object = "index.html"
  price_class         = var.cloudfront_price_class

  origin {
    domain_name              = aws_s3_bucket.frontend.bucket_regional_domain_name
    origin_id                = aws_s3_bucket.frontend.id
    origin_access_control_id = aws_cloudfront_origin_access_control.frontend.id
  }

  dynamic "origin" {
    for_each = var.enable_ai_origin ? [1] : []
    content {
      domain_name              = local.ai_origin_domain
      origin_id                = local.ai_origin_id
      origin_access_control_id = aws_cloudfront_origin_access_control.ai_service[0].id

      custom_origin_config {
        http_port              = 80
        https_port             = 443
        origin_protocol_policy = "https-only"
        origin_ssl_protocols   = ["TLSv1.2"]
        # Q&A takes 14-27s and a precompute miss 50-58s; the default 30s would
        # cut the latter off. 60 is the maximum without a quota increase.
        origin_read_timeout = 60
      }
    }
  }

  # Note: the 403/404 -> index.html custom_error_response below also applies
  # here, so a signing failure reaches the browser as HTML with status 200.
  # The frontend client treats a non-JSON response as an error.
  dynamic "ordered_cache_behavior" {
    for_each = var.enable_ai_origin ? [1] : []
    content {
      path_pattern             = "/api/ai"
      allowed_methods          = ["DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"]
      cached_methods           = ["GET", "HEAD"]
      target_origin_id         = local.ai_origin_id
      viewer_protocol_policy   = "https-only"
      cache_policy_id          = data.aws_cloudfront_cache_policy.caching_disabled.id
      origin_request_policy_id = data.aws_cloudfront_origin_request_policy.all_viewer_except_host.id
    }
  }

  default_cache_behavior {
    allowed_methods        = ["GET", "HEAD"]
    cached_methods         = ["GET", "HEAD"]
    target_origin_id       = aws_s3_bucket.frontend.id
    viewer_protocol_policy = "redirect-to-https"
    cache_policy_id        = data.aws_cloudfront_cache_policy.caching_optimized.id

    function_association {
      event_type   = "viewer-request"
      function_arn = aws_cloudfront_function.slides_index.arn
    }
  }

  # react-router uses client-side routing, so any path S3 can't find (403/404)
  # falls back to index.html and lets the SPA handle the route.
  custom_error_response {
    error_code         = 403
    response_code      = 200
    response_page_path = "/index.html"
  }

  custom_error_response {
    error_code         = 404
    response_code      = 200
    response_page_path = "/index.html"
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
  }

  tags = {
    Project     = var.project_name
    Environment = var.environment
  }
}

# Only this distribution may call the AI Service Function URL. Function URLs
# with AWS_IAM auth need both actions granted to CloudFront's service principal.
resource "aws_lambda_permission" "cloudfront_invoke_ai_url" {
  count = var.enable_ai_origin ? 1 : 0

  statement_id           = "AllowCloudFrontInvokeFunctionUrl"
  action                 = "lambda:InvokeFunctionUrl"
  function_name          = var.ai_function_name
  principal              = "cloudfront.amazonaws.com"
  source_arn             = aws_cloudfront_distribution.frontend.arn
  function_url_auth_type = "AWS_IAM"
}

resource "aws_lambda_permission" "cloudfront_invoke_ai" {
  count = var.enable_ai_origin ? 1 : 0

  statement_id  = "AllowCloudFrontInvokeFunction"
  action        = "lambda:InvokeFunction"
  function_name = var.ai_function_name
  principal     = "cloudfront.amazonaws.com"
  source_arn    = aws_cloudfront_distribution.frontend.arn
}

resource "aws_s3_bucket_policy" "frontend" {
  bucket = aws_s3_bucket.frontend.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "AllowCloudFrontOAC"
        Effect    = "Allow"
        Principal = { Service = "cloudfront.amazonaws.com" }
        Action    = "s3:GetObject"
        Resource  = "${aws_s3_bucket.frontend.arn}/*"
        Condition = {
          StringEquals = {
            "AWS:SourceArn" = aws_cloudfront_distribution.frontend.arn
          }
        }
      }
    ]
  })
}
