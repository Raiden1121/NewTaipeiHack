import type { WebFinding, WebSearchSettings } from '../types/webFinding.js';

/**
 * 網路搜尋的抽象。
 *
 * 為什麼要抽象：Bedrock 的原生 Web Search **只支援 OpenAI GPT 模型**，走
 * `bedrock-mantle` 的 Responses API；我們推論用的 Claude 走 `bedrock-runtime`
 * 的 Converse API，兩條路完全不同。把搜尋抽出來，之後要換成別的搜尋服務
 * （Tavily、Brave…）或改用自架索引，只要換這一層。
 *
 * 也讓「關閉」變成一個實作而不是一堆 if：`DisabledWebSearchProvider`。
 */
export interface WebSearchProvider {
  /** 給日誌與錯誤訊息用的描述。 */
  readonly description: string;
  /**
   * 執行搜尋。
   *
   * 可以丟錯（HTTP 失敗、逾時等）—— `runFeature()` 會捕捉，把原因寫進
   * limitations，然後照原本的資料繼續回答。搜尋是加分功能，
   * 它掛掉不該讓使用者拿到 502。
   *
   * **但實作必須自己設逾時。** 沒有逾時的話，一個慢掉的搜尋會把整個 Lambda
   * 拖到 API Gateway 超時，使用者看到的會是 504 而不是「搜尋失敗」。
   */
  search(query: string, settings: WebSearchSettings): Promise<WebSearchResult>;
}

export interface WebSearchResult {
  findings: WebFinding[];
  /**
   * 必須寫進輸出 limitations 的說明。
   * 例如「已啟用網路搜尋」、「搜尋失敗，本次未使用網路資料」。
   */
  notes: string[];
}

/**
 * 關閉狀態的實作。前端那顆開關沒打開時就是這個。
 *
 * 刻意不回 notes：沒開搜尋是預設狀態，不需要在每個回應的 limitations
 * 裡都寫一句「你沒有開網路搜尋」，那是雜訊。
 */
export class DisabledWebSearchProvider implements WebSearchProvider {
  readonly description = 'web-search(disabled)';

  async search(): Promise<WebSearchResult> {
    return { findings: [], notes: [] };
  }
}

/** 給測試用：回傳預先準備好的結果。 */
export class StaticWebSearchProvider implements WebSearchProvider {
  readonly description = 'web-search(static)';

  constructor(
    private readonly findings: WebFinding[],
    private readonly notes: string[] = [],
  ) {}

  async search(): Promise<WebSearchResult> {
    return { findings: [...this.findings], notes: [...this.notes] };
  }
}

/**
 * 每次搜尋最多採用幾筆結果。
 *
 * 就算 contextSize 設 high（最多 25 筆觀察值），我們也只取前 8 筆進 prompt。
 * 理由是 prompt 長度直接影響延遲，而延遲已經是這個服務最大的風險
 * （單次 15–21 秒，API Gateway 上限 29/30 秒）。
 */
export const MAX_WEB_FINDINGS = 8;
