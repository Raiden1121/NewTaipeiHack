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

variable "enable_ai_origin" {
  description = "Route /api/ai on this distribution to the AI Service Lambda Function URL. A separate flag rather than checking ai_function_url, because the URL is unknown until the Lambda exists and count cannot depend on unknown values."
  type        = bool
  default     = false
}

variable "ai_function_url" {
  description = "AI Service Lambda Function URL (module.ai_service.function_url), e.g. https://abc.lambda-url.us-west-2.on.aws/. Used when enable_ai_origin is true."
  type        = string
  default     = ""
}

variable "ai_function_name" {
  description = "AI Service Lambda function name, granted to this distribution via resource-based permissions. Used when enable_ai_origin is true."
  type        = string
  default     = ""
}
