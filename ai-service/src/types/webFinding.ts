import { z } from 'zod';

/**
 * 一筆網路搜尋結果。
 *
 * ⚠️ **這跟 `AiEvidence` 是刻意分開的兩個型別，不要合併。**
 *
 * `AiEvidence` 代表「資料管線產出、可追溯、可重現的指標」；`WebFinding` 代表
 * 「從網路上找到的一段文字」。兩者的可信度完全不同層級：
 * - evidence 有 `source` / `sourcePath` / `fetchedAt`，任何人可以回頭核對同一個數字
 * - web finding 只有一個網址和一段摘要，明天可能就變了
 *
 * 如果把它們塞進同一個陣列，模型的 basis 裡就會出現「內政部戶政司的人口數」
 * 和「某個網頁的說法」並列 —— 使用者是青年局，他們拿這個做政策判斷。
 * 型別分開是為了讓這件事在結構上不可能發生。
 */
export const WebFindingSchema = z.object({
  /** `web:1`、`web:2`…。輸出的 webReferences 要引用這個值。 */
  findingId: z.string().min(1),
  title: z.string(),
  url: z.string().url(),
  /** 搜尋服務回傳的摘要。**這是不可信輸入**，見 guardrails 的 prompt injection 防範。 */
  snippet: z.string(),
  /** 來源頁面的發布日期，搜尋服務沒提供時為 null。 */
  publishedDate: z.string().nullable(),
  /** 我們取得這筆結果的時間。用來讓使用者判斷新舊。 */
  retrievedAt: z.string(),
});
export type WebFinding = z.infer<typeof WebFindingSchema>;

/**
 * 搜尋要不要限定在可信來源。
 *
 * - `trusted`：只搜 `TRUSTED_SOURCE_DOMAINS` 這份白名單（政府與學術網域）。
 *   來源清單乾淨，但找不到東西的機率高很多 —— 很多有用的產業背景不在 gov.tw 上。
 * - `all`：全網搜尋。背景資訊豐富，但社群平台的內容也會進來。
 *
 * 為什麼要做成開關而不是選一個：兩種模式各有適用場合，而且**這是一個政策判斷，
 * 不是技術判斷**。對外的正式報告會希望只引用官方來源；內部要理解一個數字為什麼
 * 長這樣時，518 的職缺頁或新聞報導往往比 gov.tw 有用得多
 * （實測「為何八里薪資高」最有解釋力的來源是 518 熊班的八里職缺頁，
 * 上面看得到台北港物流理貨、月薪 42,000–47,000 —— 那種資訊政府網站不會有）。
 */
export const WebSearchScopeSchema = z.enum(['trusted', 'all']);
export type WebSearchScope = z.infer<typeof WebSearchScopeSchema>;

/**
 * `trusted` 模式的網域白名單。
 *
 * 用**網域後綴**比對（Tavily 的 `include_domains` 支援），所以 `gov.tw` 會涵蓋
 * `www.ris.gov.tw`、`web.wra.gov.tw`、`youth.ntpc.gov.tw` 等等。
 *
 * 收錄原則：發布者有官方問責的來源。
 * - `gov.tw`：中央與地方政府
 * - `edu.tw`：學術機構
 * - `moi.gov.tw` / `dgbas.gov.tw` / `mol.gov.tw` 已被 `gov.tw` 涵蓋，不重複列
 * - `stat.gov.tw` 同理
 *
 * 刻意**不含**新聞網域：新聞有編輯品質但沒有官方問責，而且一旦開始列就會變成
 * 「哪家算可信」的爭論。需要新聞的時候用 `all`，並依賴 `webReferences` 與
 * `basis` 分離＋「未經驗證」標註來管理可信度。
 */
export const TRUSTED_SOURCE_DOMAINS: readonly string[] = ['gov.tw', 'edu.tw'];

/**
 * AI Service 的共用搜尋設定 schema。直接注入 context 時 `enabled` 預設為 false；
 * 公開 top-level query 的預設由 `buildAiContext` 套用為 enabled/all/low。
 */
export const WebSearchSettingsSchema = z.object({
  enabled: z.boolean().default(false),
  /**
   * 搜尋回傳的上下文量，對應 Bedrock Web Search 的 `search_context_size`：
   * low≈5 筆、medium≈11 筆、high≈25 筆觀察值。
   * 預設 low —— 筆數越多 input token 越多，而延遲已經是這個服務的痛點。
   */
  contextSize: z.enum(['low', 'medium', 'high']).default('low'),
  /**
   * 只信任來源還是全網。預設 `all`。
   *
   * 預設全網的理由：這個服務的 Q&A 定位是**數據解釋**，而解釋一個數字為什麼長這樣
   * 需要的產業與地理背景，大多不在政府網站上。預設 `trusted` 會讓多數「為什麼」
   * 問題搜不到東西，等於預設放棄解釋能力。
   *
   * 要改成預設只收官方來源：設 `WEB_SEARCH_SCOPE=trusted`。
   */
  scope: WebSearchScopeSchema.default('all'),
});
export type WebSearchSettings = z.infer<typeof WebSearchSettingsSchema>;

export const DEFAULT_WEB_SEARCH_SETTINGS: WebSearchSettings = {
  enabled: false,
  contextSize: 'low',
  scope: 'all',
};
