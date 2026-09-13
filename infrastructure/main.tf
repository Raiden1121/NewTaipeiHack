# Add future services as their own module block here
# (e.g. module "backend" { source = "./modules/backend" ... }).

module "frontend" {
  source = "./modules/frontend"

  project_name           = var.project_name
  environment            = var.environment
  cloudfront_price_class = var.cloudfront_price_class
}

module "analytics_table" {
  source = "./modules/analytics_table"

  project_name = var.project_name
  environment  = var.environment
}

module "api" {
  source = "./modules/api"

  project_name        = var.project_name
  environment         = var.environment
  dynamodb_table_name = module.analytics_table.table_name
  dynamodb_table_arn  = module.analytics_table.table_arn
}

module "raw_data" {
  source = "./modules/raw_data"

  project_name = var.project_name
  environment  = var.environment
}

module "ai_service" {
  source = "./modules/ai_service"

  project_name             = var.project_name
  environment              = var.environment
  bedrock_model_id         = var.bedrock_model_id
  tavily_api_key           = var.tavily_api_key
  backend_lambda_role_name = module.api.lambda_role_name
  # ai-service 讀 evidence 的來源跟 backend 是同一張表。傳表名會讓它切成
  # AI_EVIDENCE_SOURCE=dynamo，傳 ARN 是為了把唯讀 IAM 權限限定在那張表。
  # ⚠️ 目前只有 `npm run precompute` 與 dev 腳本會用到 —— handler 的 evidence
  # 從 request body 進來，見 modules/ai_service/variables.tf 的說明。
  analytics_table_name = module.analytics_table.table_name
  analytics_table_arn  = module.analytics_table.table_arn

  # frontend/ and ai-service/ are npm workspaces sharing one node_modules at
  # the repo root, so this module's `npm ci` wipes and reinstalls the very tree
  # `npm run build` is reading. Run in parallel they race: npm ci hits EPERM on
  # the in-use esbuild binary and vite loses modules mid-wipe. Serialize them.
  depends_on = [null_resource.build_frontend]
}

module "transformed_data" {
  source = "./modules/transformed_data"

  project_name = var.project_name
  environment  = var.environment
}

module "analytics_lambda" {
  source = "./modules/analytics_lambda"

  project_name            = var.project_name
  environment             = var.environment
  transformed_bucket_name = module.transformed_data.bucket_name
  transformed_bucket_arn  = module.transformed_data.bucket_arn
  dynamodb_table_name     = module.analytics_table.table_name
  dynamodb_table_arn      = module.analytics_table.table_arn
}

# `terraform apply` always rebuilds and redeploys the frontend, so the
# CloudFront-served site matches whatever is currently in frontend/src.

resource "null_resource" "build_frontend" {
  triggers = {
    always_run = timestamp()
  }

  provisioner "local-exec" {
    working_dir = "${path.module}/../frontend"
    command     = "npm run build"
  }
}

resource "null_resource" "deploy_frontend" {
  depends_on = [null_resource.build_frontend]

  triggers = {
    always_run = timestamp()
  }

  provisioner "local-exec" {
    working_dir = "${path.module}/../frontend"
    command     = "aws s3 sync dist s3://${module.frontend.bucket_name} --delete --exclude slides/*"
  }

  # Windows' mimetypes lookup (used by `aws s3 sync`) often has no/wrong
  # registry entry for .js, uploading it as text/plain. Browsers refuse to
  # execute a <script type="module"> with a non-JS content-type, so re-tag
  # it explicitly after the sync.
  provisioner "local-exec" {
    working_dir = "${path.module}/../frontend"
    command     = "aws s3 cp dist s3://${module.frontend.bucket_name} --recursive --exclude * --include *.js --content-type application/javascript --metadata-directive REPLACE"
  }

  provisioner "local-exec" {
    command = "aws cloudfront create-invalidation --distribution-id ${module.frontend.cloudfront_distribution_id} --paths /*"
  }
}

# Static slide deck (slides/index.html + PDF), served from the same
# frontend bucket/distribution under the /slides/ path. No build step needed.

resource "null_resource" "deploy_slides" {
  triggers = {
    always_run = timestamp()
  }

  provisioner "local-exec" {
    working_dir = "${path.module}/.."
    command     = "aws s3 sync slides s3://${module.frontend.bucket_name}/slides --delete"
  }

  provisioner "local-exec" {
    command = "aws cloudfront create-invalidation --distribution-id ${module.frontend.cloudfront_distribution_id} --paths /slides/*"
  }
}
