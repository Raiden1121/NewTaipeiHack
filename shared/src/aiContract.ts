/**
 * AI Service 的跨模組 contract。
 *
 * 公開查詢使用 `AiQueryRequest`；帶 `context` 的 `AiRequest` 是 AI Service
 * 內部／測試形狀，不是 API Gateway 的公開 request。
 *
 * 權威實作在 `ai-service/src/types/`（那邊是 zod schema，會實際驗證）。
 * 這裡是純 TypeScript 型別，刻意不依賴任何套件，讓 frontend / backend 都能直接引用。
 * 兩邊欄位不一致時，以 ai-service 的 zod schema 為準。
 *
 * 命名規則：**pipeline 的 snake_case 欄位一律 1:1 對應成 camelCase**，不發明語意名稱。
 * 例如 `youth_eligibility` → `youthEligibility`（不是 `ageQualifier`）。
 * snake_case ↔ camelCase 的轉換只發生在 ai-service 的 `src/context/` 一層。
 */

// `PeriodType` / `YouthEligibility` 的單一定義在 `metrics.ts`。這裡原本各自
// 宣告了一份（值相同），兩份併存會讓改其中一邊時另一邊靜默不動 —— 見 `index.ts`。
import type { PeriodType, YouthEligibility } from './metrics.js';

// ---------------------------------------------------------------------------
// Evidence：AI 可以引用的單一資料點
// ---------------------------------------------------------------------------

/** 對應 data-pipeline `transform/common.py` 的 GEO_LEVELS。 */
export type GeoLevel = 'district' | 'county' | 'national' | 'organization';

/** 對應 AGE_SCOPES。 */
export type AgeScope =
  | 'exact_18_35'
  | 'derived_18_35'
  | 'official_age_group_proxy'
  | 'all_ages'
  | 'not_age_specific';

/**
 * 這個數字是從哪個欄位讀出來的：
 * - `metric_id`：資料集本身定義的指標（population、movement、youth_budgets… 以及未來 analytics 的複合指標）
 * - `record_field`：單筆記錄上的某個欄位（例如單一職缺的薪資下限）。**單筆不代表全區水準。**
 *
 * 兩者都是照抄來源的值，AI Service 不做任何運算。
 */
export type MetricSource = 'metric_id' | 'record_field';

/** 來源類型。網路搜尋引用使用獨立的 `WebFinding`，不混入 `AiEvidence`。 */
export type SourceKind = 'dataset' | 'document' | 'web';

export interface AiEvidence {
  /** 唯一識別碼。格式 `{dataset}:{period}:{recordIndex}:{metricId}`，輸出的 basis 會引用它。 */
  evidenceId: string;
  /** canonical dataset 名稱（`job_vacancies` 不是 `job_vacancy`）。 */
  dataset: string;
  /** 來源系統識別碼，例如 `moi_household_registration`。 */
  source: string | null;
  sourceRecordId: string | null;
  /** 這筆資料在來源端的網址（逐筆層級）。 */
  sourceUrl: string | null;
  sourceKind: SourceKind;
  geoLevel: GeoLevel | null;
  districtId: string | null;
  districtName: string | null;
  /** ROC 期間字串，例如 `11507`。 */
  period: string;
  periodStart: string | null;
  periodEnd: string | null;
  periodType: PeriodType | null;
  metricId: string;
  metricSource: MetricSource;
  /**
   * 指標數值。
   *
   * ⚠️ 刻意限制成純量。curated record 每一筆都帶著 `raw_record`（原始整包），
   * 如果這裡允許物件，那些東西會被一路帶進 prompt 與 API 回應。
   */
  value: number | string | null;
  unit: string | null;
  ageScope: AgeScope | null;
  /**
   * 對應 YOUTH_ELIGIBILITY，且與 `ageScope` 是強制對應關係：
   * - `exact_18_35` / `derived_18_35` → `eligible`：可證明涵蓋 18–35 歲，可當青年核心資料
   * - `official_age_group_proxy` → `proxy_only`：官方年齡組，非精確 18–35，解讀要保留
   * - `all_ages` / `not_age_specific` → `context_only`：**不可**當青年專屬數據解讀
   *
   * 前端呈現時建議把 `proxy_only` 與 `context_only` 明確標示出來，
   * 不要讓使用者以為所有數字都是青年專屬統計。
   */
  youthEligibility: YouthEligibility | null;
  /** 來源端的資料品質旗標，例如 `query_district_mismatch_filtered`。 */
  qualityFlags: string[];
  /** curated 檔案相對路徑，或 DB 參照。用來回溯這筆數字是從哪裡來的。 */
  sourcePath: string;
  fetchedAt: string | null;
}

// ---------------------------------------------------------------------------
// Request
// ---------------------------------------------------------------------------

export type AiAction = 'explain' | 'policyCopilot' | 'qa';

/** 公開 Backend → AI Service 的查詢 request；不包含 evidence/context。 */
export interface AiQueryRequest {
  action: AiAction;
  question?: string | null;
  focusDistrict?: string | null;
  focusArea?: string | null;
  /** ROC 年（114）或 ROC 月（11507）。 */
  period?: string | null;
  webSearch?: Partial<WebSearchSettings>;
}

/**
 * 前端／公開 query「開啟上網搜尋」按鈕對應的設定。
 *
 * 公開 query 預設開啟、範圍為全網；上網搜尋仍會犧牲部分可追溯性，回應會把
 * web references 與 data evidence 分開標示。
 *
 * AI Service 會依此設定使用既有 web-search provider；公開 query 預設開啟全網搜尋。
 * 找不到結果或 provider 失敗時，回應會保留 limitation，而不把網路內容混入
 * data evidence。
 * 前端可以照這個 contract 先把按鈕做好。
 */
export interface WebSearchSettings {
  enabled: boolean;
  /** 全網或只搜 gov.tw / edu.tw。公開 query 預設 all。 */
  scope?: 'all' | 'trusted';
  /** 搜尋回傳的上下文量。low≈5 筆、medium≈11 筆、high≈25 筆。預設 low。 */
  contextSize?: 'low' | 'medium' | 'high';
}

/** 一筆網路搜尋結果。跟 `AiEvidence` 是不同型別，可信度層級不同。 */
export interface WebFinding {
  findingId: string;
  title: string;
  url: string;
  snippet: string;
  publishedDate: string | null;
  retrievedAt: string;
}

export interface AiRequestContext {
  /** 僅供 AI Service 內部 context injection、本機工具與測試；不屬於公開 API。 */
  /** Data Explanation 情境可為 null；`qa` 必填。 */
  question: string | null;
  focusDistrict: string | null;
  /** 例如 `employment`、`housing`、`population`、`resources`。 */
  focusArea: string | null;
  /**
   * 內部 context injection 的搜尋設定。直接傳 context 時省略代表關閉；
   * 公開 query 省略時由 `buildAiContext` 套用 enabled/all/low 預設。
   *
   * 搜尋由 AI Service 執行，前端**不需要**自己送 `webFindings`。
   */
  webSearch?: WebSearchSettings;
  /**
   * 空陣列是合法的。「這一區這個主題沒有資料」是正常狀態，不是錯誤，
   * HTTP 仍然是 200。
   *
   * 空 evidence 時的行為取決於 `webSearch.enabled`：
   * - 關閉 → 不呼叫模型，直接回 `dataSufficiency: 'insufficient'`
   * - 開啟 → **仍然會執行搜尋**。搜到東西就用網路資料回答
   *   （`basis` 為空、`webReferences` 有內容）；搜不到才回 `insufficient`
   */
  evidence: AiEvidence[];
  /**
   * 呼叫端已知的資料限制（例如「僅取樣 200 筆／共 3896 筆」）。
   * 這些字串**保證**會原封不動出現在回應的 `limitations` 裡。
   */
  knownLimitations?: string[];
}

/** AI Service handler 的內部／測試 request；公開 API 不接受這個 context 欄位。 */
export interface AiServiceInternalRequest extends AiQueryRequest {
  context: AiRequestContext;
}

/** @deprecated 請在跨模組公開 API 使用 AiQueryRequest；此 alias 僅保留內部相容性。 */
export type AiRequest = AiServiceInternalRequest;

// ---------------------------------------------------------------------------
// Response
// ---------------------------------------------------------------------------

/**
 * 資料充足程度。獨立成欄位是為了讓前端可以可靠判斷要不要改變呈現方式，
 * 而不是去剖析 `limitations` 裡的中文。
 *
 * - `sufficient`：evidence 足以回答
 * - `partial`：部分面向缺漏，結論只在有資料的範圍內成立
 * - `insufficient`：資料不足，四塊內容**保證**都是空陣列，只有 limitations 有內容
 */
export type DataSufficiency = 'sufficient' | 'partial' | 'insufficient';

export interface BasisCitation {
  /** 一定是 context 裡真的存在的 evidenceId。AI Service 會驗證，捏造的會被拒絕。 */
  evidenceId: string;
  /** 這筆 evidence 如何支持前面的判斷，會寫出資料提供者名稱。 */
  note: string | null;
}

/** 網路來源引用。跟 `BasisCitation` 分開，因為可信度層級不同。 */
export interface WebReference {
  /** 一定是這次搜尋結果裡真的存在的 findingId。捏造的會被拒絕。 */
  findingId: string;
  /** 這筆網路資料補充了什麼，語氣會是「根據網路資料…」。 */
  note: string | null;
}

/**
 * 結構化輸出。三個 action 共用同一個型別，但**填法不同**：
 *
 * | action | `answer` | 四塊分析 |
 * |---|---|---|
 * | `explain` / `policy` | 一律 `null` | 有內容（這是它們的主要產出） |
 * | `qa` | **一定有內容** | 通常是空陣列，只有政策類問題才有 |
 *
 * 前端接 Q&A（聊天框）時**顯示 `answer` 就好**；四塊如果非空可以額外展開。
 * 接 Dashboard 卡片時看四塊，`answer` 會是 null。
 */
export interface StructuredOutput {
  dataSufficiency: DataSufficiency;
  /**
   * 直接回答使用者的問題。**只有 `action: 'qa'` 會有值，其他 action 是 `null`。**
   *
   * 這是聊天框應該顯示的內容：一段完整的話，被問到數值時第一句就會給出數值與單位。
   *
   * 保證：`action: 'qa'` 時一定非空。即使資料不足，也會是「目前沒有這個資料，
   * 無法回答」這類明確說明，而不是空字串。
   */
  answer: string | null;
  /** 問題辨識。Q&A 在純查值問題時是空陣列。 */
  issues: string[];
  /** 發展優勢。Q&A 在純查值問題時是空陣列。 */
  strengths: string[];
  /** 資源缺口。Q&A 在純查值問題時是空陣列。 */
  resourceGaps: string[];
  /** 政策方向。Q&A 在純查值問題時是空陣列。 */
  policyDirections: string[];
  /**
   * 判斷依據。**只會引用資料管線的 evidence，不會有網路來源。**
   *
   * 保證：只要上面四塊有任何內容，**或 `answer` 有內容且 `dataSufficiency` 不是
   * `insufficient`**，`basis` 或 `webReferences` 至少有一筆
   * （「有結論就要有可追溯的依據」是 schema 強制的）。
   *
   * 也就是說 Q&A 的回答同樣受這條規則保護 —— 不會出現一句沒有任何依據的答案。
   *
   * `basis` 為空但 `webReferences` 非空 = **純網路回答**，代表資料管線完全沒有
   * 相關指標。這種情況 `limitations` 一定會有一條明確說明「本次沒有資料管線的
   * 官方統計，以下內容僅來自網路搜尋」。建議前端在這個狀態顯示明顯的視覺區隔。
   */
  basis: BasisCitation[];
  /**
   * 網路來源引用。跟 `basis` 分開是刻意的 —— 前端要能區分
   * 「這句話有官方統計支撐」和「這句話是某個網頁說的」。
   *
   * 保證：`webReferences` 非空時，`dataSufficiency` 一定不是 `sufficient`
   * （需要上網補充代表管線資料有缺口），而且 `limitations` 一定會有一條
   * 說明部分內容來自網路搜尋。
   *
   * 建議前端在有網路來源時顯示明確的視覺區隔。
   */
  webReferences: WebReference[];
  /** 資料限制。沒有限制時是空陣列，不會省略這個欄位。 */
  limitations: string[];
  /** 保證包含「不代表政府正式政策決定」字樣。 */
  disclaimer: string;
}

/**
 * 資料來源標註。
 *
 * ⚠️ **這是程式從實際被 `basis` 引用的 evidence 推導出來的，不是 LLM 產生的。**
 * 網址與機關名稱是最容易被 LLM 編得像真的東西，所以模型碰不到這個欄位。
 * 前端請直接渲染這個結構，不要去 `output` 的中文裡找來源。
 */
export interface SourceAttribution {
  /** 來源系統識別碼，例如 `moi_household_registration`。 */
  sourceId: string;
  /** 中文資料提供機關，例如「內政部戶政司」。registry 沒登記時為 null。 */
  organization: string | null;
  /** 中文資料集名稱。 */
  datasetLabel: string | null;
  kind: SourceKind;
  /** 資料集層級的官方頁面，供查證用（不是 API endpoint）。 */
  url: string | null;
  /** 逐筆層級網址（例如某份預算書 PDF、某個職缺頁面），最多 3 筆。 */
  recordUrls: string[];
  /** 用到這個來源的 canonical dataset 名稱。 */
  datasets: string[];
  /** 實際被 basis 引用的 evidenceId。 */
  citedEvidenceIds: string[];
  /** curated 檔案路徑或 DB 參照。 */
  sourcePaths: string[];
  /** 這批 evidence 裡最新的抓取時間，讓使用者知道資料多舊。 */
  fetchedAt: string | null;
}

export interface AiSuccessResponse {
  action: AiAction;
  /**
   * 產生這份回應的模型，例如 `bedrock(us.anthropic.…, us-west-2, auth=sigv4)`
   * 或 `mock(no network)`。
   *
   * 前端建議在非正式模型（`mock`）時顯示明顯標示 —— demo 當天忘記設環境變數
   * 卻沒人發現，是很現實的風險。
   */
  generatedBy: string;
  /**
   * 這份結果是預先算的還是即時算的。
   *
   * - `hit`：回的是批次預先算好的結果，`precomputedAt` 是它**當初**產生的時間
   * - `miss`：快取開著但沒有這一筆，已即時計算
   * - `disabled`：伺服器端沒有設快取位置
   * - `bypass`：這個 action 不快取（`qa` 永遠是這個，因為問法無限多種）
   *
   * 背景：`explain` 與 `policyCopilot` 沒有使用者問題，輸出是
   * （行政區, 主題, 那批 evidence）的純函數，實測各要 50 與 58 秒，
   * 超過 API Gateway HTTP API 固定的 30 秒上限，所以正式路徑走預先算。
   */
  cache: AiCacheStatus;
  /**
   * 預先算的產生時間（ISO 8601），`cache` 不是 `hit` 時是 null。
   *
   * **前端請把它顯示出來**（例如「分析產生於 X」）：使用者看到的卡片可能是
   * 幾小時前算的，不講就等於暗示它是剛剛算的。
   */
  precomputedAt: string | null;
  output: StructuredOutput;
  /** **一定存在。** 沒有引用任何資料時是空陣列（此時 dataSufficiency 是 insufficient）。 */
  sources: SourceAttribution[];
}

/** 見 `AiSuccessResponse.cache`。 */
export type AiCacheStatus = 'hit' | 'miss' | 'disabled' | 'bypass';

export interface AiErrorResponse {
  error: string;
  code?: string;
  /** request 格式錯誤（HTTP 400）時的逐欄位訊息。 */
  issues?: { path: string; message: string }[];
}

/**
 * HTTP 狀態碼約定：
 * - `200`：成功。**包含「資料不足」** —— 那是正常結果，不是錯誤。
 * - `400`：公開 `AiQueryRequest` 不符合格式，`issues` 會列出逐欄位問題。
 * - `502`：格式沒問題但執行失敗（Bedrock 不可用、模型輸出反覆不合 schema、
 *   引用了不存在的 evidenceId）。呼叫端可以重試。
 * - `503`：AI Service 沒有設定正式 evidence source。
 * - `504`：同步 invoke 超時。
 */
export type AiResponse = AiSuccessResponse | AiErrorResponse;
