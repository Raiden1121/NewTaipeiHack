# One Lambda serves all 5 read endpoints from api_contract.md (health,
# catalog, dashboard/overview, districts/{id}, analyses/{id}) — routing is
# done inside handler.py, so API Gateway just proxies everything to it.
# handler.py reads pre-computed analytics from the DynamoDB table below;
# whatever loads data-pipeline's published snapshot into that table is a
# separate program, not part of this Lambda.
#
# The same Lambda also serves POST /api/v1/ai/{action} — the bridge that
# reads DynamoDB, assembles an AiRequestContext, and invokes the ai-service
# Lambda (see handler.py's module docstring and ai-service/DEPLOYMENT.md
# section 1). That route is deliberately NOT exposed through the API
# Gateway HTTP API below — see the aws_lambda_function_url resource at the
# bottom of this file for why.

data "archive_file" "lambda" {
  type        = "zip"
  source_dir  = "${path.module}/lambda"
  output_path = "${path.module}/lambda.zip"
}

resource "aws_iam_role" "lambda_exec" {
  name = "${var.project_name}-api-lambda-exec"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })

  tags = {
    Project     = var.project_name
    Environment = var.environment
  }
}

resource "aws_iam_role_policy_attachment" "lambda_logs" {
  role       = aws_iam_role.lambda_exec.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# Read-only — handler.py doesn't call DynamoDB yet, this just means no infra
# change is needed when it does. See infrastructure/dynamodb_schema.md.
resource "aws_iam_role_policy" "dynamodb_read" {
  name = "${var.project_name}-api-dynamodb-read"
  role = aws_iam_role.lambda_exec.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["dynamodb:GetItem", "dynamodb:BatchGetItem", "dynamodb:Query"]
      Resource = var.dynamodb_table_arn
    }]
  })
}

# Lets this Lambda's POST /api/v1/ai/{action} route invoke ai-service
# directly. The reverse grant (ai-service's role allowed to be invoked by
# this role) already exists in modules/ai_service/main.tf's
# aws_iam_role_policy.allow_backend_invoke — that grant was sitting unused
# until this route existed to call it.
resource "aws_iam_role_policy" "invoke_ai_service" {
  name = "${var.project_name}-api-invoke-ai-service"
  role = aws_iam_role.lambda_exec.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = "lambda:InvokeFunction"
      Resource = var.ai_service_lambda_arn
    }]
  })
}

resource "aws_lambda_function" "api" {
  function_name    = "${var.project_name}-api"
  role             = aws_iam_role.lambda_exec.arn
  handler          = "handler.handler"
  runtime          = "python3.12"
  timeout          = var.timeout
  filename         = data.archive_file.lambda.output_path
  source_code_hash = data.archive_file.lambda.output_base64sha256

  environment {
    variables = {
      ANALYTICS_TABLE_NAME   = var.dynamodb_table_name
      AI_SERVICE_LAMBDA_NAME = var.ai_service_lambda_name
    }
  }

  tags = {
    Project     = var.project_name
    Environment = var.environment
  }
}

resource "aws_apigatewayv2_api" "api" {
  name          = "${var.project_name}-api"
  protocol_type = "HTTP"

  cors_configuration {
    allow_origins = ["*"]
    allow_methods = ["GET", "OPTIONS"]
    allow_headers = ["*"]
  }

  tags = {
    Project     = var.project_name
    Environment = var.environment
  }
}

resource "aws_apigatewayv2_integration" "lambda" {
  api_id                 = aws_apigatewayv2_api.api.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.api.invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "default" {
  api_id    = aws_apigatewayv2_api.api.id
  route_key = "$default"
  target    = "integrations/${aws_apigatewayv2_integration.lambda.id}"
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.api.id
  name        = "$default"
  auto_deploy = true
}

resource "aws_lambda_permission" "apigw" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.api.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.api.execution_arn}/*/*"
}

# POST /api/v1/ai/{action} goes through this instead of the HTTP API above.
# Reason: AWS API Gateway HTTP APIs have a hard, non-configurable 30-second
# integration timeout (there is no setting to raise it — REST API Gateway
# caps out the same way). Live Q&A alone measures 14-30s
# (ai-service/.env.example's latency table) before any semantic-validation
# retry, which BEDROCK_MAX_ATTEMPTS defaults to allowing once. Routing that
# through the same Gateway as the sub-second dashboard reads risks random
# demo-day timeouts for no benefit. A Function URL has no such ceiling — it
# just inherits this Lambda's own `timeout` (var.timeout above) — so the
# GET reads keep using API Gateway unchanged, and only this POST route uses
# the Function URL.
resource "aws_lambda_function_url" "ai_proxy" {
  function_name      = aws_lambda_function.api.function_name
  authorization_type = "NONE" # hackathon: no auth anywhere yet, same caveat as modules/ai_service/main.tf's Lambda

  cors {
    allow_origins = ["*"]
    allow_methods = ["POST", "OPTIONS"]
    allow_headers = ["content-type"]
  }
}
