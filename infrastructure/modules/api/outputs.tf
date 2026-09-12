output "api_endpoint" {
  value = aws_apigatewayv2_api.api.api_endpoint
}

output "lambda_function_name" {
  value = aws_lambda_function.api.function_name
}
