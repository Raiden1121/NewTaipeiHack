# Add future services as their own module block here
# (e.g. module "backend" { source = "./modules/backend" ... }).

module "frontend" {
  source = "./modules/frontend"

  project_name           = var.project_name
  environment            = var.environment
  cloudfront_price_class = var.cloudfront_price_class
}

module "api" {
  source = "./modules/api"

  project_name = var.project_name
  environment  = var.environment
}

module "raw_data" {
  source = "./modules/raw_data"

  project_name = var.project_name
  environment  = var.environment
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
    command     = "aws s3 sync dist s3://${module.frontend.bucket_name} --delete"
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
