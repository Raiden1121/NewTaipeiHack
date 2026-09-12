# Analytics job: reads curated data from the transformed-data bucket, runs the
# same analytics as `data-pipeline/src/run_analytics.py`, and writes the
# DynamoDB items defined by infrastructure/dynamodb_schema.md.
#
# Container image rather than a zip: the analytics needs shapely/pyproj native
# wheels, and the job needs the large ephemeral storage and memory that only
# make sense paired with an image. It is deliberately NOT on a schedule or an
# endpoint — invoke it explicitly (see infrastructure.md), because a run reads
# gigabytes of curated data and rewrites the whole table.

locals {
  # Everything the image is built from: the handler here, plus the analytics
  # package and config it imports out of data-pipeline/. __pycache__ churns on
  # every local run, so hashing it would rebuild the image for no source change.
  source_files = concat(
    [
      for file in fileset("${var.pipeline_dir}", "src/**") : "${var.pipeline_dir}/${file}"
      if !strcontains(file, "__pycache__")
    ],
    [for file in fileset("${var.pipeline_dir}", "config/**") : "${var.pipeline_dir}/${file}"],
    [
      for file in fileset("${path.module}/lambda", "**") : "${path.module}/lambda/${file}"
      if !strcontains(file, "__pycache__")
    ],
    ["${var.pipeline_dir}/requirements.txt", "${path.module}/Dockerfile"],
  )

  image_tag     = substr(sha1(join("", [for file in local.source_files : filesha1(file)])), 0, 16)
  image_uri     = "${aws_ecr_repository.analytics.repository_url}:${local.image_tag}"
  registry_host = split("/", aws_ecr_repository.analytics.repository_url)[0]
  dockerfile    = "${path.module}/Dockerfile"
}

resource "aws_ecr_repository" "analytics" {
  name = "${var.project_name}-analytics"

  # Images are rebuilt from source on demand, so keeping them past a destroy
  # buys nothing and blocks the repository from being removed.
  force_delete = true

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = {
    Project     = var.project_name
    Environment = var.environment
  }
}

# Tagged by source hash, so an unchanged tree neither rebuilds nor redeploys.
resource "null_resource" "build_image" {
  triggers = {
    image_tag = local.image_tag
  }

  provisioner "local-exec" {
    command = "aws ecr get-login-password --region ${var.aws_region} | docker login --username AWS --password-stdin ${local.registry_host}"
  }

  # Context is the repo root: the image needs this module's handler and
  # data-pipeline/ together. .dockerignore keeps data-pipeline/data/ out.
  provisioner "local-exec" {
    working_dir = var.repo_root
    command     = "docker build --platform linux/amd64 -f ${abspath(local.dockerfile)} -t ${local.image_uri} ."
  }

  provisioner "local-exec" {
    command = "docker push ${local.image_uri}"
  }
}

resource "aws_iam_role" "analytics_exec" {
  name = "${var.project_name}-analytics-lambda-exec"

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

resource "aws_iam_role_policy_attachment" "analytics_logs" {
  role       = aws_iam_role.analytics_exec.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "analytics_data" {
  name = "${var.project_name}-analytics-lambda-data"
  role = aws_iam_role.analytics_exec.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["s3:GetObject"]
        Resource = "${var.transformed_bucket_arn}/*"
      },
      {
        Effect   = "Allow"
        Action   = ["s3:ListBucket"]
        Resource = var.transformed_bucket_arn
      },
      {
        Effect   = "Allow"
        Action   = ["dynamodb:PutItem", "dynamodb:BatchWriteItem", "dynamodb:DescribeTable"]
        Resource = var.dynamodb_table_arn
      },
    ]
  })
}

resource "aws_lambda_function" "analytics" {
  function_name = "${var.project_name}-analytics"
  role          = aws_iam_role.analytics_exec.arn
  package_type  = "Image"
  image_uri     = local.image_uri
  timeout       = var.timeout
  memory_size   = var.memory_size

  # Curated inputs are downloaded to /tmp on demand; population alone is ~1.8GB.
  ephemeral_storage {
    size = var.ephemeral_storage_size
  }

  environment {
    variables = {
      TRANSFORMED_BUCKET   = var.transformed_bucket_name
      ANALYTICS_TABLE_NAME = var.dynamodb_table_name
    }
  }

  depends_on = [null_resource.build_image]

  tags = {
    Project     = var.project_name
    Environment = var.environment
  }
}
