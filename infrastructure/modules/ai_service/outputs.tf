output "lambda_function_name" {
  value = aws_lambda_function.ai_service.function_name
}

output "lambda_function_arn" {
  value = aws_lambda_function.ai_service.arn
}

output "lambda_role_arn" {
  value = aws_iam_role.ai_service_exec.arn
}
