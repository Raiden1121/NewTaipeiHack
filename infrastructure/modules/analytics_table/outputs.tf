output "table_name" {
  value = aws_dynamodb_table.analytics.name
}

output "table_arn" {
  value = aws_dynamodb_table.analytics.arn
}
