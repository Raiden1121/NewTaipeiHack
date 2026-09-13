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

variable "bedrock_model_id" {
  description = "Bedrock model / inference profile ID for the AI Service Lambda. See infrastructure/modules/ai_service/variables.tf for the latency tradeoffs behind the default."
  type        = string
  default     = "us.anthropic.claude-sonnet-4-6"
}

variable "tavily_api_key" {
  description = "Tavily API key for the AI Service's web search (optional -- falls back to a rate-limited keyless client if unset). Set via TF_VAR_tavily_api_key or a gitignored .tfvars file, never commit it."
  type        = string
  default     = ""
  sensitive   = true
}
