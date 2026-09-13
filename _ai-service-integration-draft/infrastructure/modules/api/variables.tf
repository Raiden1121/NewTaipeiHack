variable "project_name" {
  description = "Prefix used for named resources."
  type        = string
}

variable "environment" {
  description = "Deployment environment tag, e.g. prod, staging."
  type        = string
}

variable "dynamodb_table_name" {
  description = "Analytics DynamoDB table name, passed to the Lambda as an env var (ANALYTICS_TABLE_NAME) that handler.py reads from."
  type        = string
}

variable "dynamodb_table_arn" {
  description = "Analytics DynamoDB table ARN the API Lambda is allowed to read from."
  type        = string
}

variable "ai_service_lambda_name" {
  description = "Function name of the ai-service Lambda (module.ai_service.lambda_function_name). Passed as AI_SERVICE_LAMBDA_NAME so handler.py's POST /api/v1/ai/{action} route knows which Lambda to invoke."
  type        = string
}

variable "ai_service_lambda_arn" {
  description = "ARN of the ai-service Lambda. This Lambda's execution role is granted lambda:InvokeFunction on it."
  type        = string
}

variable "timeout" {
  description = <<-EOT
    Lambda timeout in seconds.

    The original 5 read-only endpoints finish well under a second. This is
    shared with the new POST /api/v1/ai/{action} bridge, though, which calls
    ai-service synchronously — Q&A alone measures 14-30s (see
    ai-service/.env.example), and BEDROCK_MAX_ATTEMPTS defaults to 2, so a
    validation retry can roughly double that. 60 covers the common case; if
    explain/policyCopilot cache misses ever route through here too, match
    ai-service's own 120s (ai_service/variables.tf).

    Raising this does not slow down the fast GET routes — it only changes
    the ceiling before a Lambda invocation is killed.
  EOT
  type        = number
  default     = 60
}
