import { DisabledWebSearchProvider, type WebSearchProvider } from './provider.js';
import { TavilyWebSearchProvider } from './tavily.js';

/**
 * 依環境變數決定用哪個搜尋實作。
 *
 * 預設是 **Tavily keyless** —— 不需要任何設定就能用（Tavily 提供免 key 的
 * `X-Tavily-Access-Mode: keyless` 模式，回應格式與付費版一致，只有 rate limit）。
 * 這樣前端那顆開關開下去就真的會搜到東西，不用先去申請帳號。
 *
 * 要不要搜尋是**每個請求**由 `context.webSearch.enabled` 決定（前端那顆按鈕）。
 * 這裡的環境變數只決定「伺服器端有沒有能力搜尋」：
 *
 * - `WEB_SEARCH_PROVIDER=off` → 整個功能在伺服器端停用，即使前端送 enabled=true
 *   也只會拿到「沒有找到相關的網路資料」。用在不想讓服務對外連網的環境。
 * - `TAVILY_API_KEY` → 有設就用 API key（額度較高），沒設就用 keyless。
 * - `TAVILY_TIMEOUT_MS` → 逾時，預設 8000。延遲預算很緊時可以調低。
 * - `WEB_SEARCH_INCLUDE_DOMAINS` → 逗號分隔的網域白名單，例如 `gov.tw`。
 *   設了就只搜這些網域 —— 想把來源收斂成只信官方網站時很有用。
 *
 * 為什麼**不用** Bedrock 原生 Web Search：它只支援 OpenAI GPT 模型且必須走
 * `bedrock-mantle` 的 Responses API，而本專案用 Claude + Converse。
 *
 * 為什麼**不用** agent 框架（Strands 等）：我們刻意做預先檢索，query 由程式決定。
 * agent 的價值是讓模型自己決定何時搜、要不要再搜一輪，那是多次 LLM 往返；
 * 而單次已經 15–26 秒、API Gateway 上限 29/30 秒，多一輪就超時。
 */
export function createWebSearchProviderFromEnv(
  env: NodeJS.ProcessEnv = process.env,
): WebSearchProvider {
  if (env.WEB_SEARCH_PROVIDER?.toLowerCase() === 'off') {
    return new DisabledWebSearchProvider();
  }

  return new TavilyWebSearchProvider({
    apiKey: env.TAVILY_API_KEY ?? null,
    timeoutMs: parsePositiveInt(env.TAVILY_TIMEOUT_MS),
    includeDomains: parseDomains(env.WEB_SEARCH_INCLUDE_DOMAINS),
  });
}

function parsePositiveInt(value: string | undefined): number | undefined {
  if (value === undefined) {
    return undefined;
  }
  const parsed = Number.parseInt(value, 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : undefined;
}

function parseDomains(value: string | undefined): string[] | undefined {
  if (value === undefined) {
    return undefined;
  }
  const domains = value
    .split(',')
    .map((domain) => domain.trim())
    .filter((domain) => domain.length > 0);
  return domains.length > 0 ? domains : undefined;
}
