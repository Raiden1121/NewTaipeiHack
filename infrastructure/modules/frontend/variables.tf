variable "project_name" {
  description = "Prefix used for named resources."
  type        = string
}

variable "environment" {
  description = "Deployment environment tag, e.g. prod, staging."
  type        = string
}

variable "cloudfront_price_class" {
  description = "CloudFront price class. PriceClass_200 includes Asia Pacific edge locations."
  type        = string
  default     = "PriceClass_200"
}
