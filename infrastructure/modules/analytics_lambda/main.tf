# Analytics job: reads curated data from the transformed-data bucket, runs the
# same analytics as `data-pipeline/src/run_analytics.py`, and writes the
# DynamoDB items defined by infrastructure/dynamodb_schema.md.
#
# A plain zip, not a container image: the only native dependencies the analytics
# import graph reaches are shapely and pyproj (~114MB unzipped, well under the
# 250MB limit), and pip fetches their Linux wheels from any build machine, so
# nothing here needs Docker. Large memory and /tmp are configurable on zip
# functions just as they are on image ones.
#
# It is deliberately NOT on a schedule or an endpoint -- invoke it explicitly
# (see infrastructure.md), because a run reads gigabytes of curated data and
# rewrites the whole table.

locals {
  pipeline_dir = "${path.module}/../../../data-pipeline"
  build_dir    = "${path.module}/build"

  # Everything the payload is built from: the handler here, plus the analytics
  # package and config it imports out of data-pipeline/. __pycache__ churns on
  # every local run, so hashing it would rebuild for no source change.
  source_files = concat(
    [
      for file in fileset(local.pipeline_dir, "src/**") : "${local.pipeline_dir}/${file}"
      if !strcontains(file, "__pycache__")
    ],
    [for file in fileset(local.pipeline_dir, "config/**") : "${local.pipeline_dir}/${file}"],
    [
      for file in fileset("${path.module}/lambda", "**") : "${path.module}/lambda/${file}"
      if !strcontains(file, "__pycache__")
    ],
    [
      "${path.module}/build.py",
      # districts.json's boundary_file points at this, so it ships too.
      "${path.module}/../../../frontend/public/Map_NewTaipei.json",
    ],
  )

  source_hash = sha1(join("", [for file in local.source_files : filesha1(file)]))
}

# Rebuilds only when the sources above change.
resource "null_resource" "build_package" {
  triggers = {
    source_hash = local.source_hash
  }

  provisioner "local-exec" {
    command = "python ${abspath("${path.module}/build.py")} --out ${abspath(local.build_dir)}"
  }
}

data "archive_file" "analytics" {
  type        = "zip"
  source_dir  = local.build_dir
  output_path = "${path.module}/lambda.zip"

  depends_on = [null_resource.build_package]
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
  function_name    = "${var.project_name}-analytics"
  role             = aws_iam_role.analytics_exec.arn
  handler          = "handler.handler"
  runtime          = "python3.12"
  timeout          = var.timeout
  memory_size      = var.memory_size
  filename         = data.archive_file.analytics.output_path
  source_code_hash = data.archive_file.analytics.output_base64sha256

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

  tags = {
    Project     = var.project_name
    Environment = var.environment
  }
}
