output "frontend_bucket_name" {
  value = module.frontend.bucket_name
}

output "frontend_cloudfront_distribution_id" {
  value = module.frontend.cloudfront_distribution_id
}

output "frontend_url" {
  value = "https://${module.frontend.cloudfront_domain_name}"
}

output "slides_url" {
  value = "https://${module.frontend.cloudfront_domain_name}/slides/"
}

output "api_endpoint" {
  value = module.api.api_endpoint
}

output "raw_data_bucket_name" {
  value = module.raw_data.bucket_name
}

output "analytics_table_name" {
  value = module.analytics_table.table_name
}

output "ai_service_lambda_name" {
  value = module.ai_service.lambda_function_name
}
