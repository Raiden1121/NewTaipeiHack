output "api_endpoint" {
  value = aws_apigatewayv2_api.api.api_endpoint
}

output "lambda_function_name" {
  value = aws_lambda_function.api.function_name
}

output "lambda_role_name" {
  value = aws_iam_role.lambda_exec.name
}
