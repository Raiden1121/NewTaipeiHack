# AI Service Lambda -- the Amazon Bedrock call boundary (ai-service/).
#
# Not fronted by API Gateway, and its Function URL is not public. This
# handler has no authentication of its own (see ai-service/DEPLOYMENT.md
# section 6) -- a public URL means anyone who finds it can run up the
# Bedrock bill, one full prompt (few-shot + evidence) per request. So the
# Function URL below uses AWS_IAM auth, and the only principal allowed to
# call it is the frontend CloudFront distribution, which signs requests
# with Origin Access Control (modules/frontend, path /api/ai). Same-account
# IAM callers can still invoke the function directly, which is what
# `backend_lambda_role_name` below grants. This also sidesteps API
# Gateway's 30s hard ceiling; CloudFront's origin read timeout is 60s.
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
  #
  # The banner defines `require` inside the ESM bundle. The AWS SDK ships as
  # CJS and calls require("node:stream") etc.; esbuild's ESM output replaces
  # those with a shim that throws "Dynamic require of ... is not supported"
  # when no real `require` exists, which crashed the Lambda at init. Keeping
  # ESM (rather than --format=cjs) matters because buildContext.ts uses
  # import.meta.url.
  provisioner "local-exec" {
    working_dir = "${path.module}/../../../ai-service"
    command     = "npx --yes esbuild@0.24.2 src/handlers/lambda.ts --bundle --platform=node --target=node22 --format=esm --outfile=dist-lambda/index.mjs \"--banner:js=import{createRequire}from'node:module';const require=createRequire(import.meta.url);\""
  }

  # Copies ai-service/.precomputed/*.json into dist-lambda/precomputed/ so the
  # zip serves explain / policyCopilot from precomputed results (see
  # AI_PRECOMPUTE_DIR below). Warns, but does not fail, when there are none.
  provisioner "local-exec" {
    working_dir = "${path.module}/../../../ai-service"
    command     = "node scripts/stage-lambda.mjs"
  }
}

data "archive_file" "ai_service" {
  type        = "zip"
  source_dir  = "${path.module}/../../../ai-service/dist-lambda"
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
  count = var.analytics_table_arn != "" ? 1 : 0

  name = "${var.project_name}-ai-service-analytics-read"
  role = aws_iam_role.ai_service_exec.id

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
      {
        BEDROCK_MODEL_ID = var.bedrock_model_id
        # Staged into the zip by scripts/stage-lambda.mjs. Must be generated
        # against this same DynamoDB table (AI_EVIDENCE_SOURCE=dynamo) or the
        # fingerprints will not match and every card recomputes live.
        AI_PRECOMPUTE_DIR = "/var/task/precomputed"
      },
      # Evidence source. ai-service defaults to reading data-pipeline's published
      # snapshot files, which do not exist in Lambda -- there is no filesystem to
      # read and the 450MB data directory is deliberately not packaged.
      #
      # These two are set together because neither is useful alone. They are
      # what lets a request omit `context` and have the handler fetch evidence
      # itself (lambda.ts resolveRequestContext). See variables.tf.
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

# IAM-auth Function URL, reachable only through the frontend CloudFront
# distribution (modules/frontend grants cloudfront.amazonaws.com, scoped to that
# distribution's ARN). Unsigned requests to this URL get 403.
resource "aws_lambda_function_url" "ai_service" {
  function_name      = aws_lambda_function.ai_service.function_name
  authorization_type = "AWS_IAM"
}

# Same-account IAM callers don't need a Lambda resource-based policy --
# their own identity policy having lambda:InvokeFunction on this ARN is
# enough. Attaching it directly to backend's existing execution role means
# backend needs zero infra changes on their end when they actually wire up
# the call; until then this grant is simply unused.
resource "aws_iam_role_policy" "allow_backend_invoke" {
  count = var.backend_lambda_role_name != "" ? 1 : 0

  name = "${var.project_name}-ai-service-invoke"
  role = var.backend_lambda_role_name

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = "lambda:InvokeFunction"
      Resource = aws_lambda_function.ai_service.arn
    }]
  })
}
