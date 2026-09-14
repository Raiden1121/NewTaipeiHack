import { apiPost } from "./client";

export type AiWebSearchScope = "all" | "trusted";

export interface AiQueryRequest {
  action: "qa";
  question: string;
  focusArea: "policy";
  webSearch: {
    enabled: true;
    scope: AiWebSearchScope;
    contextSize: "low";
  };
}

export interface AiQueryResponse {
  action: "qa";
  generatedBy: string;
  output: {
    answer: string | null;
  };
}

export function queryAi(request: AiQueryRequest): Promise<AiQueryResponse> {
  return apiPost<AiQueryResponse>("/api/v1/ai/query", request);
}
