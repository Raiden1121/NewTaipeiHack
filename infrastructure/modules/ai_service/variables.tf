variable "project_name" {
  description = "Prefix used for named resources."
  type        = string
}

variable "environment" {
  description = "Deployment environment tag, e.g. prod, staging."
  type        = string
}

variable "bedrock_model_id" {
  description = <<-EOT
    Bedrock model or cross-Region inference profile ID (see ai-service/.env.example
    for how to look up what your account can actually use). Defaults to Claude
    Haiku 4.5 because it's the only model that reliably finishes an AI Service
    request in ~10-15s; Opus/Sonnet run 30-75s (ai-service/DEPLOYMENT.md section 5).
    Switching to Opus is fine as long as nothing downstream of this Lambda imposes
    a ~30s timeout on its caller (e.g. an API Gateway HTTP API integration would).
  EOT
  type    = string
  default = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
}

variable "timeout" {
  description = "Lambda timeout in seconds. 120 covers Opus's observed 74s worst case plus one semantic-validation retry (BEDROCK_MAX_ATTEMPTS default 2). Drop to 60 if bedrock_model_id is a Haiku model."
  type        = number
  default     = 120
}

variable "memory_size" {
  description = "Lambda memory in MB. This Lambda is I/O-bound (waiting on Bedrock/Tavily); more memory won't make it faster."
  type        = number
  default     = 512
}

variable "tavily_api_key" {
  description = "Tavily API key for web search. Web search defaults to ON for every request (buildAiContext's default is enabled: true); without a key it falls back to a keyless client with a low rate limit that can get hit during a demo with several concurrent users."
  type        = string
  default     = ""
  sensitive   = true
}

variable "web_search_scope" {
  description = "Server-side default for AiRequestContext.webSearch.scope: '' (leave as code default, currently 'all') or 'trusted' (gov.tw / edu.tw only). Users can still request either scope unless web_search_include_domains also restricts it."
  type        = string
  default     = ""
}

variable "web_search_include_domains" {
  description = "Comma-separated domain allowlist that no request-level scope can bypass. Leave empty for no hard limit."
  type        = string
  default     = ""
}

variable "web_search_provider" {
  description = "Set to 'off' to disable web search entirely regardless of any request-level scope. Leave empty to keep it on."
  type        = string
  default     = ""
}

variable "backend_lambda_role_name" {
  description = "IAM role name of the backend API Lambda (module.api's aws_iam_role.lambda_exec name, exposed as module.api.lambda_role_name), granted lambda:InvokeFunction on this AI Service Lambda so backend can call it directly once it implements that call. Leave empty to skip granting -- nothing invokes this Lambda yet (see infrastructure.md)."
  type        = string
  default     = ""
}
