variable "project_name" {
  description = "Prefix used for named resources."
  type        = string
}

variable "environment" {
  description = "Deployment environment tag, e.g. prod, staging."
  type        = string
}

variable "dynamodb_table_name" {
  description = "Analytics DynamoDB table name, passed to the Lambda as an env var (not read yet — handler.py still serves mock data)."
  type        = string
}

variable "dynamodb_table_arn" {
  description = "Analytics DynamoDB table ARN the API Lambda is allowed to read from."
  type        = string
}
