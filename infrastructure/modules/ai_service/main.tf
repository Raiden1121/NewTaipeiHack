# AI Service Lambda -- the Amazon Bedrock call boundary (ai-service/).
#
# Deliberately NOT fronted by API Gateway or a Lambda Function URL. This
# handler has no authentication at all (see ai-service/DEPLOYMENT.md
# section 6) -- exposing it publicly means anyone who finds the URL can
# run up the Bedrock bill, one full prompt (few-shot + evidence) per
# request, at whatever model's price. Instead, invocation is authorized
# purely through IAM: same-account callers don't need a resource-based
# policy (aws_lambda_permission) at all, just `lambda:InvokeFunction` on
# their own identity policy, which is what `backend_lambda_role_name`
# below grants. The public API boundary owns the 28-second synchronous budget;
# this private Lambda remains independently configurable for direct diagnostic
# invokes and does not expose its own HTTP endpoint.
#
# Packaging uses esbuild rather than `npm run build` (tsc): tsc only
# transpiles TypeScript, it doesn't bundle node_modules, and the Lambda
# Node runtime does not ship @aws-sdk/client-bedrock-runtime by default.
# The bundle is emitted as `index.mjs` specifically so Node loads it as
# ESM without also having to carry a `"type": "module"` package.json into
# the zip (ai-service/package.json sets that, but esbuild's bundle
# doesn't otherwise know to bring it along).
#
# Every `terraform apply` rebuilds the bundle, same as the frontend build in
# the root module -- keeps this in sync with whatever is currently in
# ai-service/src without a separate release step, which fits a hackathon's
# pace but is worth revisiting later. Dependencies come from the repo-root
# `npm install` (workspaces), not from here; see the provisioner below.

resource "null_resource" "build_ai_service" {
  triggers = {
    always_run = timestamp()
  }

  # One command per provisioner. A multi-line `command` runs through
  # `cmd /C` on Windows, which does not treat the newline as a separator: only
  # the first line executed, the bundle was never written, and cmd still
  # returned 0 so this resource reported success while archive_file failed on
  # the missing file.
  #
  # No `npm ci` here: ai-service is an npm workspace, so installing from this
  # directory rewrites the repo-root node_modules that frontend/ shares, which
  # left the frontend build without react/tailwind on the next apply. The root
  # install already provides these deps, and esbuild is fetched by `npx --yes`.
  provisioner "local-exec" {
    working_dir = "${path.module}/../../../ai-service"
    command = "npx --yes esbuild@0.24.2 src/handlers/lambda.ts --bundle --platform=node --target=node22 --format=esm --main-fields=module,main --outfile=dist-lambda/index.mjs"
  }
}

data "archive_file" "ai_service" {
  type        = "zip"
  source_file = "${path.module}/../../../ai-service/dist-lambda/index.mjs"
  output_path = "${path.module}/ai-service-lambda.zip"

  depends_on = [null_resource.build_ai_service]
}

resource "aws_iam_role" "ai_service_exec" {
  name = "${var.project_name}-ai-service-lambda-exec"

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

resource "aws_iam_role_policy_attachment" "ai_service_logs" {
  role       = aws_iam_role.ai_service_exec.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

data "aws_region" "current" {}
data "aws_caller_identity" "current" {}

# Cross-Region inference profiles need permission on TWO ARNs: the profile
# itself, and the foundation model in every region the profile can route
# to. Granting only the first gets an AccessDeniedException that does not
# say the second is missing (ai-service/DEPLOYMENT.md section 3). The
# foundation-model resource is scoped to `anthropic.*` rather than `*` --
# loose enough to survive swapping bedrock_model_id between Anthropic
# models, tight enough not to be a blanket Bedrock grant.
resource "aws_iam_role_policy" "bedrock_invoke" {
  name = "${var.project_name}-ai-service-bedrock-invoke"
  role = aws_iam_role.ai_service_exec.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = ["bedrock:InvokeModel"]
      Resource = [
        "arn:aws:bedrock:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:inference-profile/${var.bedrock_model_id}",
        "arn:aws:bedrock:*::foundation-model/anthropic.*",
      ]
    }]
  })
}

# Read-only access to the analytics table (the AI Context store).
#
# ai-service reads evidence from DynamoDB at request time -- see
# ai-service/src/context/dynamoRepository.ts. It needs exactly two actions:
# BatchGetItem for the normal path (one round trip for all the items a request
# needs) and GetItem because the SDK falls back to it for single-key reads.
#
# No write actions on purpose: ai-service must never modify the analytics store.
# Writing is data-pipeline's job (modules/analytics_lambda). A read-only grant
# means a bug in the prompt layer cannot corrupt the dashboard's data source.
#
# No Query/Scan either: the table's schema is designed so every access pattern
# is a plain key lookup (infrastructure/dynamodb_schema.md), and granting Scan
# on a table that will grow is how a cheap request turns into an expensive one.
resource "aws_iam_role_policy" "analytics_table_read" {
  count = var.analytics_table_read_enabled ? 1 : 0

  name = "${var.project_name}-ai-service-analytics-read"
  role = aws_iam_role.ai_service_exec.id

  lifecycle {
    precondition {
      condition     = var.analytics_table_arn != ""
      error_message = "analytics_table_arn must be set when analytics_table_read_enabled is true."
    }
  }

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["dynamodb:GetItem", "dynamodb:BatchGetItem"]
      Resource = var.analytics_table_arn
    }]
  })
}

resource "aws_lambda_function" "ai_service" {
  function_name    = "${var.project_name}-ai-service"
  role             = aws_iam_role.ai_service_exec.arn
  handler          = "index.handler"
  runtime          = "nodejs22.x"
  timeout          = var.timeout
  memory_size      = var.memory_size
  filename         = data.archive_file.ai_service.output_path
  source_code_hash = data.archive_file.ai_service.output_base64sha256

  environment {
    variables = merge(
      { BEDROCK_MODEL_ID = var.bedrock_model_id },
      # Evidence source. The deployed handler reads the published projection from
      # DynamoDB; local snapshot files are only for local development/tests and
      # are deliberately not packaged into Lambda.
      #
      # These two are set together because neither is useful alone.
      var.analytics_table_name != ""
      ? { ANALYTICS_TABLE_NAME = var.analytics_table_name, AI_EVIDENCE_SOURCE = "dynamo" }
      : {},
      var.tavily_api_key != "" ? { TAVILY_API_KEY = var.tavily_api_key } : {},
      var.web_search_scope != "" ? { WEB_SEARCH_SCOPE = var.web_search_scope } : {},
      var.web_search_include_domains != "" ? { WEB_SEARCH_INCLUDE_DOMAINS = var.web_search_include_domains } : {},
      var.web_search_provider != "" ? { WEB_SEARCH_PROVIDER = var.web_search_provider } : {},
    )
  }

  tags = {
    Project     = var.project_name
    Environment = var.environment
  }
}

# Same-account IAM callers don't need a Lambda resource-based policy --
# their own identity policy having lambda:InvokeFunction on this ARN is
# enough. Attach it directly to the existing API Lambda execution role: the
# `POST /api/v1/ai/query` route uses this grant for its synchronous invoke.
resource "aws_iam_role_policy" "allow_backend_invoke" {
  count = var.backend_lambda_invoke_enabled ? 1 : 0

  name = "${var.project_name}-ai-service-invoke"
  role = var.backend_lambda_role_name

  lifecycle {
    precondition {
      condition     = var.backend_lambda_role_name != ""
      error_message = "backend_lambda_role_name must be set when backend_lambda_invoke_enabled is true."
    }
  }

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = "lambda:InvokeFunction"
      Resource = aws_lambda_function.ai_service.arn
    }]
  })
}
