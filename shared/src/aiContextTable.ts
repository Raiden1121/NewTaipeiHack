/**
 * DynamoDB「AI Context」表的形狀提案 —— **提案，還沒定案，有意見直接改。**
 *
 * ===========================================================================
 * 給 data-pipeline / analytics 的人：只看這三件事就夠了
 * ===========================================================================
 *
 * 1️⃣ **資料來源欄位請拆成兩個**，不要只有一個：
 *      source    : 'moi_household_registration'   ← 機關/系統識別碼
 *      sourceUrl : 'https://…'                    ← 能點進去的網址（可為 null）
 *
 *    理由：只有 `source` 的話使用者只看到機關名稱、無法查證；
 *    只有 `sourceUrl` 的話沒辦法穩定分組、也顯示不出中文機關名。
 *    AI Service 每個回應都必須附資料來源，兩個都要才做得到。
 *
 * 2️⃣ **複合指標必須帶 `computation`**，說明算法與母體大小：
 *      computation: 'median of house_prices.price_per_ping, n=1832, period=11507'
 *
 *    理由：AI 引用「板橋區房價中位數 58.3 萬/坪」時，六塊輸出的「判斷依據」與
 *    「資料限制」都要交代這個數字的來歷。沒有它 AI 只能寫「資料顯示」，那就是黑箱。
 *    原始指標（直接來自 curated、沒有計算）可以是 null。
 *
 * 3️⃣ **key schema 請照下面的 `AiContextTableKeys`。** 這是唯一事後很難改的東西
 *    （改 key 等於重灌資料），所以先講。三個 access pattern 的理由見下方註解。
 *
 *    至於 `metricId` 叫什麼名字，**AI Service 完全不在意** —— 程式不 hard-code
 *    任何 metric 名稱。你愛怎麼命名都行，只要同一個指標保持穩定就好。
 *
 * ===========================================================================
 *
 * 背景：架構圖上這條線是
 * `Deterministic Analytics → DynamoDB / AI Context → Backend API + AI Service`，
 * 也就是 AI Service 正式的 evidence 來源是這張表，不是本機 curated 檔案。
 *
 * 由 ai-service 先提是因為那邊進度最快，等定案只會變成回頭改。
 *
 * ⚠️ 這份提案還沒有實作驗證過 —— AI Service 目前跑的是本機 curated 檔案那條路
 * （`ai-service/src/context/curatedFileRepository.ts`），DynamoDB 實作還沒寫。
 */

/**
 * AI Service 需要的三種存取模式，key schema 是為了滿足這三種而設計的：
 *
 * 1. **某一區、某期間的全部指標** → Dashboard Data Explanation
 *    `Query PK = "DISTRICT#65000010" AND begins_with(SK, "11507#")`
 *
 * 2. **某個指標橫跨 29 區** → Data Q&A 的比較題（「哪一區職缺最多」）
 *    `Query GSI1 PK = "METRIC#youth_18_35_total" AND begins_with(GSI1SK, "11507#")`
 *
 * 3. **全市／機關層級指標** → 青年局預算、全國人才需求
 *    `Query PK = "SCOPE#organization" AND begins_with(SK, "116#")`
 */
export interface AiContextTableKeys {
  /** `DISTRICT#<districtId>`，或非行政區層級用 `SCOPE#<geoLevel>`。 */
  PK: string;
  /** `<period>#<metricId>` */
  SK: string;
  /** GSI1 partition key：`METRIC#<metricId>` */
  GSI1PK: string;
  /** GSI1 sort key：`<period>#<districtId>`（非行政區層級用 `<period>#<geoLevel>`） */
  GSI1SK: string;
}

/**
 * item 屬性。除了下面特別註明的，欄位語意與 `AiEvidence` 完全相同
 * （見 `aiContract.ts`），這樣 AI Service 可以直接映射，不需要另一套轉換規則。
 */
export interface AiContextItem extends AiContextTableKeys {
  dataset: string;
  source: string;
  sourceRecordId: string | null;
  /**
   * 這筆資料在來源端的網址。
   *
   * 這對應到「DB 新增一欄位是資料來源」那件事。建議**兩個欄位都要**，
   * 不要只有一個：
   * - `source`：機關／系統識別碼（`moi_household_registration`），用來查中文機關名稱
   * - `sourceUrl`：能點進去的網址，讓使用者自己查證
   *
   * 只有 `source` 的話使用者只看到機關名稱，沒辦法驗；只有 `sourceUrl` 的話
   * 沒辦法穩定分組與顯示中文機關名。
   */
  sourceUrl: string | null;
  sourceKind: 'dataset' | 'document' | 'web';

  geoLevel: 'district' | 'county' | 'national' | 'organization';
  districtId: string | null;
  districtName: string | null;

  period: string;
  periodStart: string | null;
  periodEnd: string | null;
  periodType: 'day' | 'month' | 'year' | 'snapshot' | null;

  metricId: string;
  /** 數值一律純量。不要把 `raw_record` 之類的原始整包塞進來。 */
  value: number | string | null;
  unit: string | null;

  ageScope: string | null;
  youthEligibility: 'eligible' | 'proxy_only' | 'context_only';
  qualityFlags: string[];
  fetchedAt: string;

  /**
   * ⭐ **複合指標必填** —— 這是 AI Service 對 analytics 產出的唯一額外要求。
   *
   * 說明這個數字是怎麼算出來的、母體多大，例如：
   * `"median of house_prices.price_per_ping, n=1832, period=11507"`
   *
   * 為什麼一定要有：AI 引用「板橋區房價中位數 58.3 萬/坪」時，六塊輸出的
   * 「判斷依據」與「資料限制」都必須交代這個數字的來歷。沒有這個欄位，
   * AI 只能寫「資料顯示」，那就是黑箱 —— 而且我們也無法在輸出裡誠實說明
   * 「這是 1,832 筆交易的中位數，不是全部成交案件」。
   *
   * 原始指標（直接來自 curated，沒有計算）可以是 null。
   */
  computation: string | null;

  /** 回溯用：這筆指標是從哪個 curated 檔案／S3 物件算出來的。 */
  sourcePath: string;
}

/**
 * 給 analytics 實作者的備註：
 *
 * 1. **`metricId` 叫什麼名字，AI Service 不在意。** 程式不 hard-code 任何 metric
 *    名稱，只讀 `metricId` 的值。要叫 `house_price_median_per_ping` 或
 *    `median_house_price` 都可以，但同一個指標請保持穩定，前端會拿它當 key。
 *
 * 2. **AI Service 不會自己算任何複合指標。** 中位數、平均、YoY、Opportunity Index、
 *    Retention Risk 全部由 analytics 產出。這是 `ai-service.md` 的邊界。
 *
 * 3. 目前 `house_prices`（5 萬筆）與 `rentals`（4.5 萬筆）是逐筆交易明細，
 *    AI Service **預設完全排除**，並在回應的 limitations 標明「居住負擔面向未涵蓋」。
 *    analytics 一旦產出各區彙總指標，它們會以一般 evidence 的形式自動被納入，
 *    AI Service 不需要改程式。
 *
 * 4. 實測 token 數：這兩個 dataset 攤平後約 838K 與 670K tokens，
 *    合計佔全部資料的 93%，遠超模型 context window。
 *    彙總成「每區 × 每指標一列」後只剩約 2K tokens。
 */
export const AI_CONTEXT_TABLE_NOTES = 'See comments in this file.' as const;
