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
    for how to look up what your account can actually use).

    Defaults to Claude Sonnet 4.6 -- the same string ai-service has been validated
    against locally (the repo root .env's MODEL_NAMME).

    An earlier version of this default was Haiku 4.5, on the reasoning that it was
    the only model finishing in ~10-15s while Sonnet/Opus ran 30-75s. That reasoning
    no longer holds: explain / policyCopilot are now served from precomputed results
    (3-5ms) instead of being computed per request, and Q&A caps its `answer` at 400
    characters, which brought every Q&A scenario to 10-30s on Sonnet. Measurements
    are in ai-service/ai-service.md's latency section.

    Sonnet is kept because it does two things Haiku is measurably worse at:
    correcting a false premise in the user's question, and noticing that two metrics
    contradict each other. That self-checking is the core of not producing
    confidently wrong answers.

    Haiku stays the fallback if latency headroom is ever needed -- but re-run
    `npm run dev:reasoning-check` after switching, because that check (does it admit
    it cannot answer?) is exactly what small models tend to lose.
  EOT
  type        = string
  default     = "us.anthropic.claude-sonnet-4-6"
}

variable "timeout" {
  description = <<-EOT
    Lambda timeout in seconds.

    Q&A on Sonnet is 10-30s, but this needs headroom for two other paths: a
    precompute cache miss recomputes explain / policyCopilot live (44-62s observed),
    and BEDROCK_MAX_ATTEMPTS defaults to 2, so a semantic-validation failure costs a
    second full generation. 120 covers both.

    Do not drop this to 60 without checking that AI_PRECOMPUTE_DIR is set and
    `npm run dev:precompute-check` passes -- otherwise a cache miss on a dashboard
    card will hit the timeout instead of just being slow.
  EOT
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

variable "analytics_table_name" {
  description = <<-EOT
    Name of the analytics DynamoDB table (module.analytics_table.table_name).

    Setting this also sets AI_EVIDENCE_SOURCE=dynamo, because those two are only
    useful together: ai-service defaults to reading data-pipeline's published
    snapshot files, which do not exist in Lambda (no filesystem, and the 450MB
    data directory is deliberately not packaged).

    The deployed request handler uses this table for Lambda self-fetch. Local
    snapshot files and context injection remain available only to local tools
    and tests. The API Lambda passes only the public query contract and never
    supplies evidence itself.
  EOT
  type        = string
  default     = ""
}

variable "analytics_table_arn" {
  description = "ARN of the analytics DynamoDB table (module.analytics_table.table_arn), used to scope the read-only IAM grant when analytics_table_read_enabled is true."
  type        = string
  default     = ""
}

variable "analytics_table_read_enabled" {
  description = "Whether to create the read-only IAM grant for the analytics table. This is a plan-time flag because analytics_table_arn can be unknown until the table is created."
  type        = bool
  default     = false
}

variable "backend_lambda_role_name" {
  description = "IAM role name of the existing API Lambda (module.api's aws_iam_role.lambda_exec name, exposed as module.api.lambda_role_name), granted lambda:InvokeFunction on this private AI Service when backend_lambda_invoke_enabled is true."
  type        = string
  default     = ""
}

variable "backend_lambda_invoke_enabled" {
  description = "Whether to create the lambda:InvokeFunction grant for the API Lambda. This is a plan-time flag because backend_lambda_role_name can be unknown until the API role is created."
  type        = bool
  default     = false
}
