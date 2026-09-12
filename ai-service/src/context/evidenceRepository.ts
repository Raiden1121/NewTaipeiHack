import type { AiEvidence, GeoLevel, YouthEligibility } from '../types/aiEvidence.js';

/**
 * Evidence 的取用介面。
 *
 * 為什麼要這層抽象：專案架構圖上 AI Service 的上游是
 * `Deterministic Analytics → DynamoDB / AI Context → AI Service`，
 * 也就是**正式路徑是讀 DynamoDB，不是讀本機 curated 檔案**。
 *
 * 但 DynamoDB table 還不存在（data-pipeline 的 analytics 正在做），如果現在直接寫死
 * DynamoDB，整個 ai-service 就會被別人的進度卡住，Bedrock 也沒辦法先驗。
 *
 * 所以這裡把「怎麼拿 evidence」抽掉，留兩個實作：
 * - `CuratedFileEvidenceRepository`：讀 data-pipeline 本機輸出。今天就能跑真實資料。
 * - `DynamoEvidenceRepository`：讀 AI Context table。等 table 存在才能驗。
 *
 * 換來源時 handler / prompt / Bedrock 那幾層完全不用動，因為 `AiEvidence` 不變：
 * analytics 算完的複合指標仍然是「某區 / 某期間 / 某指標 / 某數值 / 某單位」。
 * 變的只是傳輸方式。
 *
 * 這跟 `src/bedrock/client.ts` 的 `createBedrockClientFromEnv()` 是同一個模式，
 * 不是另一套新架構。
 */
export interface EvidenceRepository {
  /** 給錯誤訊息與 limitations 用的來源描述，例如 `curated-files(../data-pipeline/data)` */
  readonly description: string;
  query(query: EvidenceQuery): Promise<EvidenceBundle>;
}

export interface EvidenceQuery {
  /**
   * canonical dataset 名稱（population / job_vacancies / youth_budgets…）。
   * 省略時代表「所有可用且允許進 LLM 的 dataset」。
   */
  datasets?: readonly string[];
  /** 行政區中文名，例如 ['板橋區', '三重區'] */
  districtNames?: readonly string[];
  /** 行政區代碼，例如 ['65000010'] */
  districtIds?: readonly string[];
  /** 指標名稱，例如 ['youth_18_35_total']。省略時不篩。 */
  metricIds?: readonly string[];
  geoLevels?: readonly GeoLevel[];
  /** dataset_index 的 output_key，例如 '11507'。省略時取該 dataset 最新的一筆。 */
  period?: string;
  youthEligibility?: readonly YouthEligibility[];
  /**
   * 使用者正在看的主題（`employment` / `housing` / `fertility` / `resources` / `policy`…）。
   *
   * 這不是篩選條件，是**取用範圍的提示**。curated repository 不理它（curated 的
   * dataset 本身就已經是主題），但 analytics repository 會用它決定要讀哪幾個
   * analysis artifact。
   *
   * 為什麼需要：analytics 快照有 7 個 artifact，全讀進來一個行政區就有 477 筆
   * evidence（實測約 118K token）。使用者在「就業」頁面問問題時，青年議題關鍵詞
   * 文字雲的 74 筆權重不會讓答案更好，只會讓它更慢更貴。這是依主題取用，
   * 不是截斷資料，所以不會造成「假裝資料充足」的問題 —— 而且會在 notes 裡
   * 說明本次讀了哪些分析。
   */
  focusArea?: string | null;
  /**
   * 每個 dataset 最多取幾筆 evidence。
   *
   * 這不是效能參數，是**防止 prompt 爆掉的必要限制**：實測 job_vacancies 攤平後
   * 約 46K tokens，house_prices 約 838K tokens，而 Claude 系列在 Bedrock 上是
   * 200K context window。沒有 limit 的話一次查詢就能打爆整個請求。
   */
  limitPerDataset?: number;
}

/**
 * 查詢結果。
 *
 * 刻意不只回 `AiEvidence[]`：呼叫端必須知道「有沒有被截斷」，否則會拿著 200 筆取樣
 * 當成全部資料去解讀，那正是 ai-service.md 禁止的「假裝資料充足」。
 * `notes` 會原封不動進到 structured output 的 limitations。
 */
export interface EvidenceBundle {
  evidence: AiEvidence[];
  /** 篩選後、截斷前的總筆數 */
  totalMatched: number;
  /** 是否因為 limitPerDataset 而被截斷 */
  truncated: boolean;
  /** 必須寫進輸出 limitations 的既知限制（來源、截斷、資料品質旗標…） */
  notes: string[];
}

/**
 * 每個 dataset 預設最多取幾筆。
 *
 * 200 這個數字的來源：4 個 long-form dataset（population 116 筆、movement 1711 筆、
 * vt_courses 2 筆、youth_budgets 20 筆）中最大的 movement 攤平後約 21K tokens；
 * 取 200 筆上限可以讓「9 個 dataset 全查」維持在 200K window 內還有餘裕放 prompt
 * 與模型輸出。要更多筆就明確指定，並接受 prompt 變大。
 */
export const DEFAULT_LIMIT_PER_DATASET = 200;

/**
 * analytics evidence 的 dataset 名稱前綴。
 *
 * 定義在這裡（而不是 `analyticsRecord.ts`）是因為 **curated repository 也需要認得它**：
 * `EvidenceQuery.datasets` 是兩個 repository 共用的欄位，呼叫端指名
 * `analytics_employment` 時，curated 那邊會去 `dataset_index.json` 找這個名字、
 * 找不到，然後在 limitations 裡寫「dataset_index 沒有 analytics_employment 的條目」——
 * 那句話會讓使用者以為資料缺漏，實際上資料好好地在另一個來源裡。
 */
export const ANALYTICS_DATASET_PREFIX = 'analytics_';

export function isAnalyticsDatasetName(dataset: string): boolean {
  return dataset.startsWith(ANALYTICS_DATASET_PREFIX);
}

/**
 * 逐筆交易明細、不做彙總就不該進 LLM 的 dataset。
 *
 * 決策 A 的具體落地：ai-service **不自己算**中位數、平均、YoY 或任何複合指標
 * （`ai-service.md` 的 Boundaries、`transform.md` 都把這些歸給 data-pipeline 的
 * `analytics/`）。
 *
 * 而這幾個 dataset 是逐筆交易，不彙總就沒有解讀價值：給模型看 200 筆房價明細，
 * 結構上就是在誘導它自己算平均——那會同時違反「不可自行推算」與「不可捏造數字」。
 * 所以預設整個排除，並在 limitations 誠實說明缺這一塊。
 *
 * 等 analytics 把「各區房價中位數」寫進 DynamoDB（帶 metric_id + value + computation），
 * 那些會以 long-form evidence 的形式自動被吃進來，這份清單不需要改。
 */
export const TRANSACTION_LEVEL_DATASETS: readonly string[] = ['house_prices', 'rentals'];

export const TRANSACTION_LEVEL_NOTE =
  '本次分析未涵蓋房價與租金資料：house_prices 與 rentals 是逐筆交易明細（各約 5 萬與 4.5 萬筆），' +
  '需要先由 data-pipeline 的 analytics 彙總成各區中位數等指標才能解讀。' +
  'AI Service 不自行計算這類複合指標，因此居住負擔面向在此次回應中缺漏。';

/**
 * analytics 已經提供的居住負擔彙總指標。
 *
 * 這幾個 metricId 一旦出現在 evidence 裡，上面那句
 * 「居住負擔面向在此次回應中缺漏」就變成**錯的**，必須換成下面那句。
 */
export const HOUSING_AGGREGATE_METRIC_IDS: readonly string[] = [
  'house_price_median',
  'house_price_median_wan',
  'rent_median',
  'rent_wage_ratio',
];

/**
 * 上面那句的替代版本：逐筆交易仍然不進 LLM，但彙總指標已經有了。
 *
 * 為什麼一定要換掉而不是兩句並存：原本那句寫著「居住負擔面向缺漏」，而
 * `runFeature()` 會強制把 knownLimitations 原封不動放進輸出的 limitations。
 * 如果不換，AI 就會一邊引用 `house_price_median = 574,657 元/坪` 一邊在限制裡
 * 宣告「本次沒有居住負擔資料」—— 自我矛盾的輸出比沒有資料更糟，因為使用者
 * 無法判斷哪一句是真的。
 */
export const TRANSACTION_LEVEL_SUPERSEDED_NOTE =
  'house_prices 與 rentals 的逐筆交易明細（各約 5 萬與 4.5 萬筆）未進入本次分析，' +
  'AI Service 也不自行計算中位數；但居住負擔面向並非缺漏 —— ' +
  'data-pipeline 的 analytics 已彙總出各區房價中位數、租金中位數與租金所得比，' +
  '本次以那些彙總指標（metricSource=analytics_metric）為依據。';

/**
 * 依 EvidenceQuery 篩選 evidence。所有 repository 實作共用，確保篩選語意一致。
 *
 * 行政區篩選有一個重要例外：**非行政區層級的資料不會被行政區條件濾掉。**
 *
 * 原因是實測踩到的：`youth_budgets` 的 `geo_level` 是 `organization`、
 * `district_name` 是 null（青年局預算是機關層級，不分區），`talent_demand` 是
 * `national`，`training_numbers` 是 `county`。如果單純用 districtName 比對，
 * 使用者一選「板橋區」，青年局預算和職訓資料就全部消失——但那些正是政策分析
 * 最需要的「資源供給側」資料，而且它們對 29 區都成立。
 *
 * 所以這裡的語意是「這一區的資料 ＋ 對所有區都適用的全市／全國脈絡資料」。
 * 要關掉這個行為就明確傳 `geoLevels: ['district']`。
 */
export function applyEvidenceFilters(
  evidence: readonly AiEvidence[],
  query: EvidenceQuery,
): AiEvidence[] {
  const filtersByDistrict = query.districtNames !== undefined || query.districtIds !== undefined;

  return evidence.filter((item) => {
    if (query.geoLevels && !includesValue(query.geoLevels, item.geoLevel)) {
      return false;
    }
    if (query.metricIds && !query.metricIds.includes(item.metricId)) {
      return false;
    }
    if (query.youthEligibility && !includesValue(query.youthEligibility, item.youthEligibility)) {
      return false;
    }

    // 只有 district 層級的資料才受行政區條件約束；county / national / organization
    // 層級是跨區脈絡，一律保留。
    if (filtersByDistrict && item.geoLevel === 'district') {
      const matchesName = query.districtNames
        ? includesValue(query.districtNames, item.districtName)
        : false;
      const matchesId = query.districtIds ? includesValue(query.districtIds, item.districtId) : false;
      if (!matchesName && !matchesId) {
        return false;
      }
    }
    return true;
  });
}

function includesValue<T extends string>(allowed: readonly T[], value: string | null): boolean {
  return value !== null && (allowed as readonly string[]).includes(value);
}

/**
 * 把 quality_flags 整理成人看得懂的 limitation 句子。
 *
 * 為什麼要做：真實資料裡 job_vacancies 有 42 筆帶
 * `query_district_mismatch_filtered` 旗標。這種來源端的資料品質問題如果不往上帶，
 * 模型會把它當成乾淨資料解讀。
 */
export function summarizeQualityFlags(evidence: readonly AiEvidence[]): string[] {
  const counts = new Map<string, number>();
  for (const item of evidence) {
    for (const flag of item.qualityFlags) {
      counts.set(flag, (counts.get(flag) ?? 0) + 1);
    }
  }
  return [...counts.entries()]
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([flag, count]) => `有 ${count} 筆資料帶有品質旗標 ${flag}，解讀時需保留。`);
}
