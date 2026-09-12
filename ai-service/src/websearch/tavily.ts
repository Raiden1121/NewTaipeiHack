import { WebFindingSchema, type WebFinding, type WebSearchSettings } from '../types/webFinding.js';
import type { WebSearchProvider, WebSearchResult } from './provider.js';

/**
 * Tavily 搜尋實作。
 *
 * 為什麼選 Tavily 而不是 Bedrock 原生 Web Search：後者只支援 OpenAI GPT 模型，
 * 走 `bedrock-mantle` 的 Responses API，而本專案用 Claude + Converse。
 *
 * 為什麼不用 Strands Agents 之類的 agent 框架包起來：我們刻意做「預先檢索」——
 * 用使用者的問題搜一次，query 由程式決定。agent 框架的價值是讓模型自己決定
 * 何時搜、搜什麼、要不要再搜一輪，那是**多次 LLM 往返**。而這個服務單次已經
 * 15–26 秒，API Gateway 的上限是 29/30 秒，多一輪就會超時。
 * 所以這裡就是一個 HTTP POST。
 */
const TAVILY_SEARCH_URL = 'https://api.tavily.com/search';

/**
 * `contextSize` → 取幾筆結果。數字對齊 Bedrock Web Search 的 `search_context_size`
 * 語意（low≈5、medium≈11、high≈25），這樣換 provider 時呼叫端的語意不用改。
 */
const RESULT_COUNT_BY_CONTEXT_SIZE: Record<WebSearchSettings['contextSize'], number> = {
  low: 5,
  medium: 11,
  high: 25,
};

/**
 * 摘要截斷長度。
 *
 * Tavily 的 `content` 有時上千字，8 筆就可能多好幾千 token。而 prompt 長度直接
 * 影響延遲，延遲又是這個服務最大的風險。600 字元大約夠模型判斷這筆結果講什麼。
 */
const MAX_SNIPPET_LENGTH = 600;

export interface TavilyWebSearchOptions {
  /**
   * Tavily API key。**留空就用 keyless 模式**（送 `X-Tavily-Access-Mode: keyless`
   * header），不需要帳號，回應格式與付費版一致，但有 rate limit。
   */
  apiKey?: string | null;
  /**
   * 逾時（毫秒）。預設 8000。
   *
   * 這個值必須明確設定：沒有逾時的話一個慢掉的搜尋會把整個 Lambda 拖到
   * API Gateway 超時，而使用者會看到 504 而不是「搜尋失敗」。
   */
  timeoutMs?: number;
  /**
   * 只搜這些網域（對應 Tavily 的 `include_domains`）。
   * 預設不限制 —— 使用者要的是通用上網搜尋。要收斂成只信官方來源時可以傳
   * `['gov.tw']` 之類的值。
   */
  includeDomains?: readonly string[];
  /** 讓測試注入假的 fetch。 */
  fetchImpl?: typeof fetch;
}

interface TavilyResult {
  url?: unknown;
  title?: unknown;
  content?: unknown;
  score?: unknown;
  published_date?: unknown;
}

export class TavilyWebSearchProvider implements WebSearchProvider {
  readonly description: string;
  private readonly apiKey: string | null;
  private readonly timeoutMs: number;
  private readonly includeDomains: readonly string[];
  private readonly fetchImpl: typeof fetch;

  constructor(options: TavilyWebSearchOptions = {}) {
    this.apiKey = options.apiKey?.trim() || null;
    this.timeoutMs = options.timeoutMs ?? 8000;
    this.includeDomains = options.includeDomains ?? [];
    this.fetchImpl = options.fetchImpl ?? fetch;
    this.description = `tavily(${this.apiKey ? 'api-key' : 'keyless'})`;
  }

  async search(query: string, settings: WebSearchSettings): Promise<WebSearchResult> {
    const headers: Record<string, string> = { 'content-type': 'application/json' };
    if (this.apiKey) {
      headers.authorization = `Bearer ${this.apiKey}`;
    } else {
      headers['X-Tavily-Access-Mode'] = 'keyless';
    }

    const response = await this.fetchImpl(TAVILY_SEARCH_URL, {
      method: 'POST',
      headers,
      body: JSON.stringify({
        query,
        max_results: RESULT_COUNT_BY_CONTEXT_SIZE[settings.contextSize],
        // basic 而不是 advanced：advanced 慢得多，而我們的延遲預算很緊。
        search_depth: 'basic',
        // 不要 raw_content：那是整頁 HTML 清理後的全文，動輒上萬字，
        // 我們只需要摘要，拿了只會爆記憶體與 token。
        include_raw_content: false,
        include_images: false,
        // 不要 Tavily 自己生成的 answer：那是**另一個模型的綜合結論**，
        // 沒辦法歸屬到具體來源，也繞過了我們所有的引用驗證。
        // 我們只要原始的 results，讓 Claude 在我們的 guardrails 下自己判讀。
        include_answer: false,
        ...(this.includeDomains.length > 0 ? { include_domains: [...this.includeDomains] } : {}),
      }),
      signal: AbortSignal.timeout(this.timeoutMs),
    });

    if (!response.ok) {
      const body = await response.text().catch(() => '');
      // 429 特別點出來：keyless 模式有 rate limit，撞到時換 API key 就好，
      // 錯誤訊息要讓人一看就知道該做什麼。
      const hint =
        response.status === 429 && !this.apiKey
          ? '（keyless 模式已達速率上限，設定 TAVILY_API_KEY 可提高額度）'
          : '';
      throw new Error(
        `Tavily 搜尋失敗：HTTP ${response.status}${hint} ${truncate(body, 200)}`.trim(),
      );
    }

    const payload = (await response.json()) as { results?: unknown };
    const retrievedAt = new Date().toISOString();
    const findings = Array.isArray(payload.results)
      ? payload.results
          .map((result, index) => toFinding(result as TavilyResult, index, retrievedAt))
          .filter((finding): finding is WebFinding => finding !== null)
      : [];

    return { findings, notes: [] };
  }
}

/**
 * Tavily result → `WebFinding`。
 *
 * 缺 url 或 title 的結果直接丟掉而不是補預設值：一筆沒有網址的「網路來源」
 * 無法被查證，留著只會讓輸出看起來有引用但實際上指不到任何地方。
 */
function toFinding(result: TavilyResult, index: number, retrievedAt: string): WebFinding | null {
  const url = typeof result.url === 'string' ? result.url : null;
  const title = typeof result.title === 'string' ? result.title : null;
  if (url === null || title === null) {
    return null;
  }

  const parsed = WebFindingSchema.safeParse({
    findingId: `web:${index + 1}`,
    title,
    url,
    snippet: truncate(typeof result.content === 'string' ? result.content : '', MAX_SNIPPET_LENGTH),
    // 一般搜尋（topic=general）通常沒有這個欄位，所以 null 是常態不是異常。
    publishedDate: typeof result.published_date === 'string' ? result.published_date : null,
    retrievedAt,
  });
  // 例如 url 不是合法網址時 safeParse 會失敗——同樣直接丟掉這一筆。
  return parsed.success ? parsed.data : null;
}

function truncate(value: string, max: number): string {
  return value.length <= max ? value : `${value.slice(0, max)}…`;
}
