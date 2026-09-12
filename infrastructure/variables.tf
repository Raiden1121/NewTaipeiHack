variable "project_name" {
  description = "Prefix used for named resources."
  type        = string
  default     = "newtaipei-youth"
}

variable "environment" {
  description = "Deployment environment tag, e.g. prod, staging."
  type        = string
  default     = "prod"
}

variable "aws_region" {
  description = "Region for the S3 bucket. CloudFront itself is global."
  type        = string
  default     = "us-west-2"
}

variable "cloudfront_price_class" {
  description = "CloudFront price class. PriceClass_200 includes Asia Pacific edge locations."
  type        = string
  default     = "PriceClass_200"
}
