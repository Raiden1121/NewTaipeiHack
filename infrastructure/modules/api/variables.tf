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

variable "ai_service_function_name" {
  description = "Fixed name of the private AI Service Lambda invoked synchronously by POST /api/v1/ai/query."
  type        = string
}
