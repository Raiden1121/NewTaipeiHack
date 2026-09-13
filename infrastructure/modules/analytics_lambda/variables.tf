variable "project_name" {
  description = "Prefix used for named resources."
  type        = string
}

variable "environment" {
  description = "Deployment environment tag, e.g. prod, staging."
  type        = string
}

variable "transformed_bucket_name" {
  description = "Bucket holding curated/ and quality/, read by the analytics."
  type        = string
}

variable "transformed_bucket_arn" {
  description = "ARN of the transformed-data bucket the Lambda may read."
  type        = string
}

variable "dynamodb_table_name" {
  description = "Analytics DynamoDB table the job writes."
  type        = string
}

variable "dynamodb_table_arn" {
  description = "ARN of the analytics DynamoDB table the job may write."
  type        = string
}

variable "memory_size" {
  description = "MB. The analytics loads every requested curated period into memory at once (~2GB of JSON), so this is near the Lambda ceiling on purpose."
  type        = number
  default     = 10240
}

variable "timeout" {
  description = "Seconds. 900 is Lambda's maximum; a full run downloads gigabytes before it computes anything."
  type        = number
  default     = 900
}

variable "ephemeral_storage_size" {
  description = "MB of /tmp for the downloaded curated data."
  type        = number
  default     = 10240
}
