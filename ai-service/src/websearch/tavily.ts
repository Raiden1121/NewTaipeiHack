import {
  TRUSTED_SOURCE_DOMAINS,
  WebFindingSchema,
  type WebFinding,
  type WebSearchScope,
  type WebSearchSettings,
} from '../types/webFinding.js';
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
 * 有網域限制時，向 Tavily 多要幾倍的結果。
 *
 * 為什麼需要：實測 `include_domains` 不是硬過濾，所以我們得自己濾（見
 * `filterByDomains`）。但只要 5 筆再自己濾，結果常常是 **0 筆** ——
 * 實測「為何八里薪資第六高？ 新北市」限定 gov.tw 時 5 筆全被濾掉。
 *
 * 而同一個查詢在不限制的情況下，第 4 名就是 `www.bali.ntpc.gov.tw` 的
 * 八里區社會救助分析 —— 官方來源其實找得到，只是被前幾名擠掉了。
 * 多要幾倍再濾就能撈到它。
 *
 * 4 倍是取捨：夠深到能撈出官方來源，又不會讓回應大到影響延遲
 * （Tavily 的 `content` 是摘要不是全文，25 筆的回應也還是很小，
 * 而實測整趟搜尋只花 750–850ms）。
 */
const DOMAIN_FILTER_OVERFETCH = 4;

/** Tavily 單次請求的結果上限，避免 overfetch 算出不合理的值。 */
const TAVILY_MAX_RESULTS = 50;

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
   * **額外**限制的網域（對應 Tavily 的 `include_domains`）。
   *
   * 這是伺服器層級的硬限制，跟每個請求的 `settings.scope` 是兩件事：
   * - `settings.scope === 'trusted'` → 用 `TRUSTED_SOURCE_DOMAINS`（使用者的選擇）
   * - `includeDomains` → 不管使用者選什麼都套用（營運者的政策）
   *
   * 兩者同時存在時取**交集**，也就是以較嚴格的那個為準 ——
   * 營運者設了限制，使用者不該能用「全網」把它繞掉。
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
    const domains = resolveIncludeDomains(settings.scope, this.includeDomains);
    const wantedCount = RESULT_COUNT_BY_CONTEXT_SIZE[settings.contextSize];
    // 有網域限制就多要幾倍，因為我們會自己再濾一次（Tavily 的 include_domains
    // 實測不是硬過濾），只要剛好的筆數常常濾完是 0 筆。
    const requestedCount =
      domains.length > 0
        ? Math.min(wantedCount * DOMAIN_FILTER_OVERFETCH, TAVILY_MAX_RESULTS)
        : wantedCount;
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
        max_results: requestedCount,
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
        ...(domains.length > 0 ? { include_domains: [...domains] } : {}),
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
    const rawFindings = Array.isArray(payload.results)
      ? payload.results
          .map((result, index) => toFinding(result as TavilyResult, index, retrievedAt))
          .filter((finding): finding is WebFinding => finding !== null)
      : [];

    // ⚠️ **自己再過濾一次，不要相信 include_domains。**
    //
    // 實測（真 API key、query「為何八里薪資第六高？ 新北市」、
    // include_domains: ['gov.tw','edu.tw']）回來的是 blog.salary.tw、
    // news.ttv.com.tw、bo6s.com.tw —— **五筆全部不在白名單內**。
    // 所以 Tavily 的 include_domains 至少對「裸網域後綴」不是硬過濾。
    //
    // 這是一個政策邊界（使用者選了「只接受可信來源」），不能外包給外部 API 的
    // 行為細節。自己比對 hostname 後綴是唯一能保證的做法。
    // 多要的那幾倍只是為了濾完還有東西，最後仍然只給呼叫端要的筆數 ——
    // 否則 prompt 會被塞進 4 倍的網路內容。
    const allowed = filterByDomains(rawFindings, domains);
    const findings = allowed.slice(0, wantedCount);
    const droppedByFilter = rawFindings.length - allowed.length;

    // 只信任來源模式一定要在輸出裡講。
    //
    // 理由：`trusted` 模式搜不到東西是**常態**（很多產業背景不在 gov.tw 上），
    // 而「沒找到」與「限制了範圍所以沒找到」對使用者是完全不同的意思 ——
    // 前者會讓人以為網路上真的沒有相關資訊。
    const notes: string[] = [];
    if (domains.length > 0) {
      notes.push(
        `本次網路搜尋限定在下列網域：${domains.join('、')}，未採用其他網站的內容。` +
          '若相關背景資訊只存在於新聞或民間網站，本次不會取得。',
      );
    }
    // 被我們自己濾掉的筆數要講出來。
    // 「搜尋沒找到」與「找到了但不符合來源限制」對使用者是不同的意思 ——
    // 後者代表「資訊存在，只是你選擇不採用」，那會影響他要不要切換成全網。
    if (droppedByFilter > 0) {
      notes.push(
        `搜尋結果中有 ${droppedByFilter} 筆因為不在允許的網域內而被排除。` +
          '如需更完整的背景資訊，可改用全網搜尋。',
      );
    }

    return { findings, notes };
  }
}

/**
 * 用 hostname 後綴比對過濾結果。
 *
 * 比對的是 **hostname**，不是整個 URL —— 用 `url.includes('gov.tw')` 會被
 * `https://evil.com/?ref=gov.tw` 這種網址騙過去。
 *
 * 後綴比對要對齊到點的邊界（`.gov.tw` 或完全相等），否則 `notgov.tw` 會通過。
 */
export function filterByDomains(
  findings: readonly WebFinding[],
  domains: readonly string[],
): WebFinding[] {
  if (domains.length === 0) {
    return [...findings];
  }
  return findings.filter((finding) => {
    let hostname: string;
    try {
      hostname = new URL(finding.url).hostname.toLowerCase();
    } catch {
      // 解析不出 hostname 的一律排除：無法確認來源就不該當可信來源用。
      return false;
    }
    return domains.some((domain) => {
      const normalized = domain.trim().toLowerCase().replace(/^\.+/, '');
      return hostname === normalized || hostname.endsWith(`.${normalized}`);
    });
  });
}

/**
 * 決定這次要送給 Tavily 的 `include_domains`。
 *
 * 兩個來源同時存在時取**交集**（以較嚴格的為準）：
 * `settings.scope` 是使用者的選擇，`configured` 是營運者設的硬限制，
 * 使用者不該能用「全網」把營運者的限制繞掉。
 */
export function resolveIncludeDomains(
  scope: WebSearchScope,
  configured: readonly string[],
): string[] {
  if (scope !== 'trusted') {
    return [...configured];
  }
  if (configured.length === 0) {
    return [...TRUSTED_SOURCE_DOMAINS];
  }
  // 交集：用後綴比對，因為兩邊都是網域後綴（`gov.tw` 要對得上 `ris.gov.tw`）。
  const intersection = TRUSTED_SOURCE_DOMAINS.filter((trusted) =>
    configured.some((domain) => domain.endsWith(trusted) || trusted.endsWith(domain)),
  );
  // 交集為空代表營運者的白名單跟可信清單沒有重疊 —— 這時以營運者的為準，
  // 因為那是硬限制。回傳空陣列會變成「不限制」，那是最糟的結果。
  return intersection.length > 0 ? intersection : [...configured];
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
