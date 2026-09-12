# Single-table store for data-pipeline's published analytics snapshot.
# Schema, item shapes, and the write contract for whatever job maintains
# this table: infrastructure/dynamodb_schema.md. Every access pattern the API needs
# is a plain GetItem/BatchGetItem by pk+sk, so no GSI.

resource "aws_dynamodb_table" "analytics" {
  name         = "${var.project_name}-analytics"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "pk"
  range_key    = "sk"

  attribute {
    name = "pk"
    type = "S"
  }

  attribute {
    name = "sk"
    type = "S"
  }

  point_in_time_recovery {
    enabled = true
  }

  tags = {
    Project     = var.project_name
    Environment = var.environment
  }
}
