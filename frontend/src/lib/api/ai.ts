// 政策分析助理的 AI Q&A 呼叫。
//
// 走同網域的 /api/ai：CloudFront 用 Origin Access Control 簽章後轉給 AI Service 的
// Lambda Function URL（AWS_IAM 授權），所以不需要 CORS，也沒有公開的 Lambda 網址。
// 契約見 ai-service/ai_api_contract.md 與 shared/src/aiContract.ts。

const AI_ENDPOINT = import.meta.env.VITE_AI_ENDPOINT || "/api/ai";

export type WebSearchScope = "all" | "trusted";

export interface AiQaResult {
  answer: string;
  /** 例如 `bedrock(us.anthropic.claude-sonnet-4-6, ...)`；`mock(no network)` 代表伺服器沒設模型。 */
  generatedBy: string;
}

export class AiRequestError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "AiRequestError";
    this.status = status;
  }
}

// CloudFront OAC 簽 Lambda Function URL 時不會自己算 body 的雜湊，
// POST 必須由瀏覽器帶 x-amz-content-sha256，否則 Lambda 回 403。
async function sha256Hex(text: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
}

function errorMessageOf(payload: unknown): string | null {
  if (typeof payload === "object" && payload !== null && "error" in payload) {
    const { error } = payload as { error?: unknown };
    if (typeof error === "string" && error.length > 0) return error;
  }
  return null;
}

export async function askPolicyQuestion(
  question: string,
  scope: WebSearchScope,
  signal?: AbortSignal,
): Promise<AiQaResult> {
  const body = JSON.stringify({ action: "qa", question, webSearch: { scope } });

  let response: Response;
  try {
    response = await fetch(AI_ENDPOINT, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "x-amz-content-sha256": await sha256Hex(body),
      },
      body,
      signal,
    });
  } catch (error) {
    if ((error as { name?: unknown } | null)?.name === "AbortError") {
      throw new AiRequestError(0, "AI 回覆逾時，請稍後再試。");
    }
    throw new AiRequestError(0, "無法連線至 AI 服務，請確認網路連線。");
  }

  // CloudFront 會把 403/404 換成 index.html 並回 200（SPA fallback），
  // 所以不能只看 status，拿到的不是 JSON 就當成失敗。
  const isJson = response.headers.get("content-type")?.includes("application/json") ?? false;
  const payload: unknown = isJson ? await response.json().catch(() => null) : null;

  if (!response.ok || payload === null) {
    const message = errorMessageOf(payload);
    throw new AiRequestError(
      response.status,
      message !== null
        ? `AI 服務回應錯誤：${message}`
        : `AI 服務目前無法使用（HTTP ${response.status}）`,
    );
  }

  const { output, generatedBy } = payload as {
    output?: { answer?: unknown };
    generatedBy?: unknown;
  };
  if (typeof output?.answer !== "string" || output.answer.length === 0) {
    throw new AiRequestError(response.status, "AI 服務回傳的格式不正確。");
  }
  return {
    answer: output.answer,
    generatedBy: typeof generatedBy === "string" ? generatedBy : "",
  };
}
