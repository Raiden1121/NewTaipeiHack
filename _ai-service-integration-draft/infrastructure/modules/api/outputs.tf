output "api_endpoint" {
  value = aws_apigatewayv2_api.api.api_endpoint
}

output "lambda_function_name" {
  value = aws_lambda_function.api.function_name
}

output "lambda_role_name" {
  value = aws_iam_role.lambda_exec.name
}

# POST /api/v1/ai/{action} lives here, not on api_endpoint above — see the
# aws_lambda_function_url resource's comment in main.tf for why.
output "ai_proxy_function_url" {
  value = aws_lambda_function_url.ai_proxy.function_url
}
