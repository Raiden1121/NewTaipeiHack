output "lambda_function_name" {
  value = aws_lambda_function.analytics.function_name
}

output "lambda_function_arn" {
  value = aws_lambda_function.analytics.arn
}

output "ecr_repository_url" {
  value = aws_ecr_repository.analytics.repository_url
}
