import { z } from 'zod';
import { WebFindingSchema, WebSearchSettingsSchema } from './webFinding.js';

/**
 * 這個檔案是 data-pipeline curated contract 在 ai-service 側的唯一鏡像。
 *
 * 欄位命名規則（決策 B）：一律是 pipeline snake_case 欄位的 1:1 camelCase 版本，
 * 不另外發明語意名稱。例如 `youth_eligibility` → `youthEligibility`，不叫
 * `ageQualifier`；`district_name` → `districtName`，不叫 `district`。
 * snake_case ↔ camelCase 的轉換只發生在 `src/context/` 這一層，其他地方一律 camelCase。
 *
 * 真實來源（已對過原始碼，不是文件推測）：
 * - `data-pipeline/src/transform/common.py` 的 `build_common_metadata()`：curated record 共同欄位
 * - `data-pipeline/src/transform/io.py` 的 `write_curated()` / `write_dataset_index()`：檔案外層與 index 形狀
 */

/** `geo_level`；來自 common.py 的 GEO_LEVELS。 */
export const GeoLevelSchema = z.enum(['district', 'county', 'national', 'organization']);
export type GeoLevel = z.infer<typeof GeoLevelSchema>;

/** `period_type`；來自 common.py 的 PERIOD_TYPES。真實資料裡可能是 null（例：vt_courses）。 */
export const PeriodTypeSchema = z.enum(['day', 'month', 'year', 'snapshot']);
export type PeriodType = z.infer<typeof PeriodTypeSchema>;

/** `age_scope`；來自 common.py 的 AGE_SCOPES。 */
export const AgeScopeSchema = z.enum([
  'exact_18_35',
  'derived_18_35',
  'official_age_group_proxy',
  'all_ages',
  'not_age_specific',
]);
export type AgeScope = z.infer<typeof AgeScopeSchema>;

/**
 * `youth_eligibility`；來自 common.py 的 YOUTH_ELIGIBILITY，且與 `age_scope` 是強制對應：
 * - `exact_18_35` / `derived_18_35` → `eligible`：可證明涵蓋 18–35 歲（含）的青年核心資料
 * - `official_age_group_proxy` → `proxy_only`：官方年齡組資料，非精確 18–35 區間，僅供參考
 * - `all_ages` / `not_age_specific` → `context_only`：不可當青年專屬數據解讀
 */
export const YouthEligibilitySchema = z.enum(['eligible', 'proxy_only', 'context_only']);
export type YouthEligibility = z.infer<typeof YouthEligibilitySchema>;

/**
 * curated record 的 `metric_id` / `value` 在真實資料裡只有 4 個 dataset 會填
 * （population、movement、vt_courses、youth_budgets），其餘 dataset 是「一筆一個實體」
 * 的寬表，數值散在 dataset 專屬欄位（position_count、total_price、training_people…）。
 *
 * 這個欄位誠實記錄某筆 evidence 的數字是從哪裡讀出來的：
 * - `metric_id`：直接取 curated record 的 `metric_id` / `value`
 * - `record_field`：取 curated dataset 專屬的數值欄位，metricId 就是該欄位名
 * - `analytics_metric`：data-pipeline 的 Deterministic Analytics **已經彙總計算完成**的
 *   指標（opportunityIndex、house_price_median、fertilityRate…），來自 published snapshot
 *
 * 三者都是「照抄檔案裡的值」，ai-service 沒有做任何運算。
 *
 * 為什麼 `analytics_metric` 必須是獨立的值、不能混進 `record_field`：解讀方式完全相反。
 * `record_field` 是單筆實體（某一個職缺的薪資下限），**不代表全區水準**；
 * `analytics_metric` 是全區彙總後的指標，**就是代表全區水準**，可以直接跨區比較。
 * 用同一個標籤會讓模型把已彙總的中位數當成單筆樣本而不敢引用，或反過來把單筆
 * 當成全區代表值 —— 兩個方向都是錯的。
 */
export const MetricSourceSchema = z.enum(['metric_id', 'record_field', 'analytics_metric']);
export type MetricSource = z.infer<typeof MetricSourceSchema>;

/**
 * 單筆 Evidence：AI Service 可以引用的一個資料點。
 *
 * `value` 刻意限制成 number / string / null，不接受物件或陣列。這不只是型別潔癖：
 * curated record 每一筆都帶著 `raw_record`（原始來源整包）與 `source_record_ids`
 * （上千個 ID），如果 value 允許物件，這些東西會直接被塞進 prompt，既爆 token
 * 也會讓模型看到未清理的原始欄位。收斂型別可以從結構上擋掉這件事。
 */
export const AiEvidenceSchema = z.object({
  evidenceId: z
    .string()
    .min(1)
    .describe('ai-service 產生的唯一識別碼，structured output 的 basis 必須引用這個值'),
  dataset: z
    .string()
    .min(1)
    .describe('canonical dataset 名稱（population / job_vacancies / youth_budgets…），不是 collector alias'),
  source: z.string().nullable().describe('curated record 的 source，例如 moi_household_registration'),
  sourceRecordId: z.string().nullable(),
  /**
   * 這筆資料在來源端的網址。
   *
   * 每個回應都必須附資料來源，而「機關名稱」比不上一個點得進去的連結。
   * 有些來源會逐筆提供（青年局預算的 PDF 網址、職缺的頁面網址），有的只能落到
   * 資料集層級的官方頁面（`SOURCE_REGISTRY` 提供）。這個欄位放前者，沒有就是 null。
   */
  sourceUrl: z.string().nullable(),
  /**
   * 來源類型，決定引用時要怎麼標示：
   * - `dataset`：政府開放資料集（目前全部都是這類）
   * - `document`：政策文件、預算書等單一文件
   * - `web`：從網路上找到的內容
   *
   * `web` 現在還沒有產生者（RAG 未實作），但型別先留著：只要有任何非資料集來源
   * 進到 context，它就必須能被標示出來，不能混在 dataset 裡看不出差別。
   */
  sourceKind: z.enum(['dataset', 'document', 'web']).default('dataset'),
  geoLevel: GeoLevelSchema.nullable(),
  districtId: z.string().nullable().describe('行政區代碼，例如 65000010；非行政區層級為 null'),
  districtName: z.string().nullable().describe('新北市 29 區之一；county / national / organization 層級為 null'),
  period: z.string().min(1).describe('dataset_index 的 output_key，ROC 期間字串，例如 11507'),
  periodStart: z.string().nullable().describe('ISO 日期'),
  periodEnd: z.string().nullable().describe('ISO 日期'),
  periodType: PeriodTypeSchema.nullable(),
  metricId: z
    .string()
    .min(1)
    .describe('指標名稱：record 的 metric_id，或（寬表 dataset）該數值欄位的欄位名'),
  metricSource: MetricSourceSchema,
  value: z
    .union([z.number(), z.string(), z.null()])
    .describe('照抄 curated 檔案的值。AI 不可竄改，也不可用它推算新數字'),
  unit: z.string().nullable(),
  /**
   * 這個數字是怎麼算出來的。**複合指標一定要有這個欄位，否則就是黑箱。**
   *
   * 直接照抄 curated 欄位的 evidence 不需要（維持 null）：值本身就是來源端的原始數字。
   * 但 `analytics_metric` 不一樣 —— 「板橋區房價中位數 574,657 元/坪」這種數字，
   * 使用者一定會問「哪來的、母體多大、哪個期間」。沒有答案的話，六塊輸出裡的
   * 「判斷依據」跟「資料限制」根本交代不過去，而 AI 也沒辦法在 basis 的 note
   * 裡誠實說明它引用的是什麼。
   *
   * 內容例如：
   * `deterministic analytics: employment.districts[].opportunityIndex`
   * `(snapshot=dev-full-20260912, calculation_version=1, upstream=job_vacancies,house_prices)`
   *
   * 這對應 `shared/src/aiContextTable.ts` 提給 data-pipeline 的 DynamoDB `computation`
   * 欄位提案 —— 換成 DynamoDB 來源時這個欄位直接沿用，不用改型別。
   */
  computation: z
    .string()
    .nullable()
    .default(null)
    .describe('複合指標的算法說明；直接照抄來源欄位的 evidence 為 null'),
  ageScope: AgeScopeSchema.nullable(),
  youthEligibility: YouthEligibilitySchema.nullable(),
  qualityFlags: z.array(z.string()).describe('curated record 的 quality_flags，沒有旗標時為空陣列'),
  sourcePath: z
    .string()
    .min(1)
    .describe('dataset_index 記錄的 curated 檔案相對路徑（index 的 `path` 欄位原值）'),
  fetchedAt: z.string().nullable().describe('curated record 的 fetched_at；缺少時為 null，不可用其他值補'),
});
export type AiEvidence = z.infer<typeof AiEvidenceSchema>;

/**
 * 一筆 evidence 的「範圍」標籤：行政區名稱，或非行政區層級的層級名稱。
 *
 * 這個函式同時被兩個地方用，而且**必須是同一個值**：
 * 1. `formatEvidenceForPrompt()` 印在 prompt 的 `scope=` 欄位
 * 2. analytics evidenceId 的第三段（見 `buildAnalyticsEvidenceId`）
 *
 * 綁在一起的原因：analytics 的 evidenceId 刻意設計成「模型可以從看得見的欄位重組」，
 * 而不是要它照抄一個不透明的流水號（實測模型會把流水號抄錯一位，導致整份分析被拒絕）。
 * 如果 prompt 顯示的 scope 和 id 裡的 scope 不一致，這個設計就失效了 ——
 * 所以只留一個實作，不讓兩邊各寫一份。
 */
export function evidenceScopeLabel(
  districtName: string | null,
  geoLevel: GeoLevel | null,
): string {
  return districtName ?? `${geoLevel ?? 'unknown'}-level`;
}

/**
 * context 的欄位定義。
 *
 * 拆成 base 是因為 `AiContextSchema` 需要加 superRefine（檢查「至少要有一種資料」），
 * 而 zod 的 `.superRefine()` 回傳 ZodEffects，之後就不能再 `.extend()`。
 * 對外的 `AiRequestContextSchema` 要加欄位，所以必須從沒有 refine 的 base 長出來。
 */
const AiContextBaseSchema = z.object({
  question: z.string().nullable().describe('使用者問題；Data Explanation 情境可為 null'),
  focusDistrict: z.string().nullable(),
  focusArea: z.string().nullable().describe('例如 employment、housing、fertility、resources'),
  /**
   * 資料管線的 evidence。
   *
   * 允許為空 —— 但前提是 `webFindings` 有內容（見下面的 superRefine）。
   * 使用者明確開啟上網搜尋時，就算管線沒有資料也應該能用網路資料回答；
   * 兩邊都空才是真的「資料不足」，那種情況不該呼叫 LLM。
   */
  evidence: z.array(AiEvidenceSchema),
  /**
   * 由 context builder 產生、必須原封不動出現在輸出 limitations 裡的既知限制。
   * 例如「只取樣 200 筆 / 共 50065 筆」、「此 dataset 標記為 context_only」。
   * 模型可以再補充，但不可刪掉這些。
   */
  knownLimitations: z.array(z.string()).default([]),
  /**
   * 網路搜尋結果。**跟 evidence 是分開的陣列，這是刻意的。**
   *
   * evidence 是資料管線產出、可追溯可重現的指標；webFindings 是網路上的一段文字。
   * 兩者可信度完全不同層級，合併就會讓「內政部戶政司的人口數」和「某個網頁的說法」
   * 在 basis 裡並列。使用者是青年局，他們拿這個做政策判斷。
   *
   * 只有前端那顆開關打開時才會有內容。
   */
  webFindings: z.array(WebFindingSchema).default([]),
});

/**
 * 一次「真的要打 LLM」的完整上下文。
 *
 * 至少要有一種資料（evidence 或 webFindings）。兩邊都空時不該呼叫模型，
 * 應該走 `buildInsufficientDataOutput()` 直接回「資料不足」
 * （見 `src/handlers/insufficientData.ts`）。
 */
export const AiContextSchema = AiContextBaseSchema.superRefine((context, ctx) => {
  // 兩邊都空就沒有任何可引用的東西，呼叫 LLM 只會得到憑空編造的內容。
  if (context.evidence.length === 0 && context.webFindings.length === 0) {
    ctx.addIssue({
      code: z.ZodIssueCode.custom,
      path: ['evidence'],
      message:
        'evidence 與 webFindings 不可同時為空：沒有任何可引用的資料就不該呼叫 LLM（應直接回傳「資料不足」）。',
    });
  }
});
export type AiContext = z.infer<typeof AiContextSchema>;

/**
 * AI Service 內部／測試用的 context injection 形狀，不是 API Gateway 公開 request。
 *
 * 跟 `AiContextSchema` 的差別：**這裡兩邊都可以是空的**。
 * 「這一區這個主題沒有資料」是要誠實回答的正常狀態，不是 400 錯誤。
 * handler 會在搜尋完成後才判斷是否真的無資料可用。
 */
export const AiRequestContextSchema = AiContextBaseSchema.extend({
  /**
   * 內部 context injection 的「開啟上網搜尋」設定。
   *
   * 直接傳 context 時省略代表關閉；公開 top-level query 省略時由
   * `buildAiContext` 套用 `enabled=true`、`scope=all`、`contextSize=low`。
   * 搜尋結果會變成 `webFindings`，所以呼叫端**不需要**自己填 `webFindings` ——
   * 那個欄位是給 AI Service 內部與測試用的。
   */
  webSearch: WebSearchSettingsSchema.default({ enabled: false, contextSize: 'low' }),
});
export type AiRequestContext = z.infer<typeof AiRequestContextSchema>;
