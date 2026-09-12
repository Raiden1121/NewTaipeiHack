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
 * 前端那顆開關對應的設定。
 *
 * 預設 `enabled: false` 是刻意的：上網搜尋會犧牲可追溯性與可重現性，
 * 所以必須是使用者明確打開的行為，不能靜默發生。
 */
export const WebSearchSettingsSchema = z.object({
  enabled: z.boolean().default(false),
  /**
   * 搜尋回傳的上下文量，對應 Bedrock Web Search 的 `search_context_size`：
   * low≈5 筆、medium≈11 筆、high≈25 筆觀察值。
   * 預設 low —— 筆數越多 input token 越多，而延遲已經是這個服務的痛點。
   */
  contextSize: z.enum(['low', 'medium', 'high']).default('low'),
});
export type WebSearchSettings = z.infer<typeof WebSearchSettingsSchema>;

export const DEFAULT_WEB_SEARCH_SETTINGS: WebSearchSettings = {
  enabled: false,
  contextSize: 'low',
};
