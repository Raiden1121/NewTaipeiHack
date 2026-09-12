import type { ApiEnvelope, ApiErrorBody } from "./types";

const BASE_URL = import.meta.env.VITE_API_BASE_URL;

export class ApiError extends Error {
  code: string;
  status: number;
  requestId?: string;

  constructor(status: number, code: string, message: string, requestId?: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.requestId = requestId;
  }
}

function isApiErrorBody(value: unknown): value is ApiErrorBody {
  return (
    typeof value === "object" &&
    value !== null &&
    "error" in value &&
    typeof (value as { error?: unknown }).error === "object"
  );
}

export async function apiFetch<T>(
  path: string,
  params?: Record<string, string | undefined>,
): Promise<ApiEnvelope<T>> {
  const url = new URL(path, BASE_URL || window.location.origin);
  if (params) {
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined) url.searchParams.set(key, value);
    }
  }

  let response: Response;
  try {
    response = await fetch(url.toString());
  } catch {
    throw new ApiError(0, "NETWORK_ERROR", "無法連線至 Backend API，請確認網路連線。");
  }

  const body: unknown = await response.json().catch(() => null);

  if (!response.ok) {
    if (isApiErrorBody(body)) {
      throw new ApiError(response.status, body.error.code, body.error.message, body.request_id);
    }
    throw new ApiError(
      response.status,
      "UNKNOWN_ERROR",
      `Backend API 回應錯誤（HTTP ${response.status}）`,
    );
  }

  return body as ApiEnvelope<T>;
}
