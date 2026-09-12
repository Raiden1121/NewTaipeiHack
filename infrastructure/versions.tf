terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # Local state for now. Point this at an S3 backend once multiple people
  # need to share state.
}

provider "aws" {
  region = var.aws_region
}
