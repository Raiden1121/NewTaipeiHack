import {
  evidenceScopeLabel,
  type AgeScope,
  type AiEvidence,
  type GeoLevel,
  type PeriodType,
  type YouthEligibility,
} from '../types/aiEvidence.js';
import { ANALYTICS_DATASET_PREFIX } from './evidenceRepository.js';

/**
 * 把 analytics published snapshot 的 artifact JSON 攤平成 `AiEvidence[]`。
 *
 * ## 為什麼是通用走訪，不是逐路徑手寫
 *
 * curated 那邊可以用 `MEASURE_FIELDS_BY_DATASET` 一個 dataset 列幾個欄位，因為
 * curated record 是平的。analytics 不是 —— 它是給 dashboard 用的巢狀結構，
 * 深度到 `annual.fertility.years[].districts[].fertilityRate`，而且每個分析的形狀
 * 都不一樣（employment 有 scatter/regression、fertility 有 fafi、participation 有
 * elections/grants/budget）。實測 6 個 analysis artifact 加起來有上百條不同的路徑。
 *
 * 手寫每一條的問題不是工作量，是**沉默失效**：pipeline 加一個新指標時，手寫的
 * 對照表不會報錯，那個指標就只是永遠不出現在 AI 的 context 裡，而沒有人會發現。
 * 通用走訪反過來 —— 新指標自動被吃進來，要排除才需要明確寫規則。
 *
 * ## 三個安全機制
 *
 * 通用走訪的風險是「什麼都吃進來」，所以有三道限制：
 *
 * 1. **`BLOCKED_KEYS`**：整段不進入的子樹（`villages` 1032 筆、`normalizedInputs`
 *    是除錯用的標準化中間值、`raw_record` 等）。
 * 2. **`METADATA_KEYS`**：進入但不產生 evidence 的欄位（`metric_id`、`generated_at`、
 *    `title`、`x_label`…）。這些是結構描述，不是可引用的數值。
 * 3. **`ANALYTICS_ARTIFACT_RULES`**：每個 artifact 的去重、欄位白名單與列數上限。
 *
 * ## 不做任何計算
 *
 * 這一層只做「選欄位、搬值、標注它是什麼」。沒有平均、沒有中位數、沒有 YoY ——
 * 那些都已經由 data-pipeline 的 Deterministic Analytics 算完了，這裡照抄，
 * 並把算法出處寫進 `computation` 讓它可追溯。
 */

/** analytics 的 evidence 一律用這個 source，對應 `SOURCE_REGISTRY` 的同名條目。 */
export const ANALYTICS_SOURCE_ID = 'newtaipei_youth_analytics';

/**
 * dataset 名稱前綴。加前綴是為了跟 curated 的 11 個 dataset 名稱不會撞。
 * 常數本身定義在 `evidenceRepository.ts`，因為 curated repository 也要認得它。
 */
export function analyticsDatasetName(artifactKey: string): string {
  return `${ANALYTICS_DATASET_PREFIX}${artifactKey}`;
}

/**
 * 整段不進入的 key。
 *
 * - `villages`：service_coverage 與 daycareCoverage 各帶 1032 筆村里明細。這是
 *   逐村里的原始明細，跟 house_prices 一樣屬於「不彙總就沒有解讀價值」，而且
 *   行政區層級的 `districts[]` 已經有彙總後的值。
 * - `normalizedInputs`：api_contract.md 明確標注「除錯用」的 16 個標準化 0–100 值。
 *   它們跟同一筆的原始指標是同一件事的兩種表示，同時給模型看只會讓它把標準化分數
 *   誤當成實際量綱（把 housing 的 87 分講成房價 87 萬）。
 * - `points`：scatter 的 29 個散佈點，x/y 都是同一個 artifact 裡已經有的指標重繪。
 *   `regression`（slope/intercept/r_squared）才是散佈圖真正的新資訊，那個保留。
 * - `sourcePeriods` / `sourcePeriod` / `source_period` / `time_policy`：期間中介資料。
 *   會被 period 解析讀到，但本身不是可引用的數值。
 */
const BLOCKED_KEYS: ReadonlySet<string> = new Set([
  'villages',
  'normalizedInputs',
  'points',
  'sourcePeriods',
  'sourcePeriod',
  'source_period',
  'time_policy',
  'raw_record',
  'raw_records',
  'source_record_ids',
  'standalone_artifacts',
  'coverage_scope_by_year',
  // ---------------------------------------------------------------------------
  // 以下是「資料完整度」與「演算法參數」，不是可引用的指標。
  //
  // `coverage` 容器：快照裡有 11 個（fertility、participation 的 6 個子分析、
  // policy_support…），內容是 district_count=29、annual_row_count=133、
  // wage_years_requested=6 這類**資料處理的統計**。實測全部 11 個容器裡
  // 沒有任何一個含 NOTE_KEYS，所以擋掉不會弄丟任何品質說明。
  //
  // 為什麼一定要擋：這些數字進了 evidence 就是「可引用的事實」，模型會拿
  // `coverage.district_count=29` 當發現寫進 basis。它是對的但毫無意義，
  // 而且會佔掉 context 上限（250 筆）裡真正指標的位置。
  'coverage',
  // 演算法參數：半徑、據點數、村里邊界數。它們決定指標怎麼算出來，
  // 本身不是量測值。radius_m=2500 被當成數據引用只會造成困惑。
  'radius_m',
  'verified_point_count',
  'excluded_point_count',
  'boundary_village_count',
  'joined_village_count',
  'population_coverage_ratio',
  // 管線列數：輸入幾列、幾列對不到行政區。屬於 pipeline 的自我檢查。
  'input_row_count',
  'unresolved_district_row_count',
  'district_count',
  'expected_district_count',
  'latest_v1_district_count',
  'latest_district_count',
  // 這兩個在 proposal_funnel 下同時出現在 coverage 裡與外面一層，
  // 外面那份擋不到，要個別列出。內容是「去重後幾筆」「幾筆要人工複核」。
  'deduplicated_item_count',
  'manual_review_required_count',
]);

/**
 * 進入但不產生 evidence 的欄位：結構描述、識別碼、圖表標籤。
 *
 * `district_id` / `district_name` / `year_roc` 這類也在這裡 —— 它們不是「數值」，
 * 而是決定其他數值屬於誰、屬於哪一期的**維度**，會被走訪過程當 context 讀走。
 */
const METADATA_KEYS: ReadonlySet<string> = new Set([
  'metric_id',
  'calculation_version',
  'config_version',
  'generated_at',
  'schema_version',
  'snapshot_id',
  'as_of',
  'normalization',
  'method',
  'title',
  'note',
  'x_label',
  'y_label',
  'signal',
  'term',
  'label',
  'name',
  'stage',
  'district_id',
  'district_name',
  'village_code',
  'election_district_code',
  'election_district_name',
  'source_datasets',
  'period_type',
  'denominator_scope',
  'population_field',
  'year',
  'year_roc',
  'election_year_roc',
  'reference_year_roc',
  'referenceYearRoc',
  'trend_coverage_scope',
  'coverage_scope',
  'election_type',
  'budget_unit',
  'execution_denominator_unit',
  // 值是年份的欄位。跟上面的 year_roc 同一類 —— 它回答「哪一年」，
  // 不是「多少」。不放這裡的話會產生一筆 metricId=budget_year_roc、
  // value=116 的 evidence，模型可能把 116 當成某個數量。
  'budget_year_roc',
  'latest_v1_year_roc',
]);

/**
 * 這些 key 會被當成「這一列在講哪個東西」的識別字，接在 metricId 後面（`metric#識別字`）。
 *
 * 沒有這個機制的話，`keywords[].weight` 攤平後 100 筆的 metricId 全叫 `weight`，
 * 模型看到一百個一模一樣的指標名而不知道哪個是「居住正義」—— 數字就失去意義了。
 */
const ROW_LABEL_KEYS: readonly string[] = ['label', 'term', 'name', 'election_district_name'];

/**
 * 從 metricId 裡拿掉的結構性容器名稱。
 *
 * `districts[].opportunityIndex` 的指標名就是 `opportunityIndex`，不需要叫
 * `districts.opportunityIndex` —— 「哪一區」已經在 districtName 欄位裡了，
 * 寫進指標名只是重複並拉長 prompt。
 */
const STRUCTURAL_PATH_KEYS: ReadonlySet<string> = new Set(['districts', 'years']);

/**
 * 允許以字串形式成為 evidence 的欄位（分級結果）。
 *
 * 其餘字串一律不產生 evidence：analytics 裡的字串幾乎都是 `status: "partial"`
 * 這類品質標記，那些屬於**限制**而不是可引用的發現，會被收集進 notes。
 * 這幾個不一樣 —— 它們是分析本身的產出結論（風險等級、友善度等級），
 * 使用者會直接問「板橋區的留才風險是高還是低」。
 */
const LEVEL_VALUE_KEYS: ReadonlySet<string> = new Set([
  'retentionRiskLevel',
  'fafiLevel',
  'fertilityLevel',
  'qualityStatus',
  'serviceCoverageStatus',
  'daycareCoverageStatus',
]);

/**
 * 會被收集成 limitations 的欄位。
 *
 * 這些是 pipeline 自己宣告的「這個數字有問題」：`blocking_reasons`（算不出來的原因）、
 * `proxy_usage`（用了代理指標）、`status: partial`。**不往上帶的後果是 AI 拿著
 * partial 的數字當完整的講** —— 例如服務涵蓋率只有 9 個據點、29 區中位數是 0，
 * 不說明就會變成「新北市青年服務資源嚴重不足」這種被資料缺漏誤導的結論。
 */
const NOTE_KEYS: ReadonlySet<string> = new Set([
  'blocking_reasons',
  'proxy_usage',
  'warnings',
  'execution_failure',
  'executionFailure',
  'availability',
  'status',
  'quality_status',
  'budget_status',
]);

/** 走訪時每個 artifact 最多產生幾筆 evidence，最後一道防爆保險。 */
export const MAX_EVIDENCE_PER_ARTIFACT = 4000;

/** 單一路徑的預設列數上限。 */
const DEFAULT_ROW_LIMIT = 120;

export interface ArtifactDedupeRule {
  /** 要跳過的 logical path（不含陣列索引） */
  path: string;
  /** 只有這個 artifact 也在同一個快照裡時才跳過 */
  ownedBy: string;
  /** 寫進 notes 的說明，讓人知道資料沒有消失、只是換地方 */
  reason: string;
}

export interface ArtifactRule {
  /** 無條件跳過的 logical path 前綴 */
  skipPaths?: readonly string[];
  /** 跳過時要附的說明（key = skipPaths 的元素） */
  skipReasons?: Readonly<Record<string, string>>;
  /** 只有在 ownedBy artifact 存在時才跳過的路徑 */
  dedupe?: readonly ArtifactDedupeRule[];
  /** 指定 logical path 只保留這些葉欄位 */
  fieldAllowlist?: Readonly<Record<string, readonly string[]>>;
  /** 指定 logical path 的列數上限 */
  rowLimits?: Readonly<Record<string, number>>;
  /** 指定 logical path 只保留 year_roc 最大的那一組 */
  latestYearOnly?: readonly string[];
}

/**
 * 每個 artifact 的規則。key 是 manifest 的 artifact key。
 *
 * 這張表的每一條都對應一個實測到的具體問題，不是預防性設定。
 */
export const ANALYTICS_ARTIFACT_RULES: Readonly<Record<string, ArtifactRule>> = {
  dashboard_overview: {
    dedupe: [
      {
        path: 'elections',
        ownedBy: 'participation',
        reason:
          'dashboard_overview 的 elections 與 analyses/participation.json 的選舉資料完全重複，' +
          '本次以 participation 為單一來源，避免同一個數字出現兩個 evidenceId。',
      },
      {
        path: 'service_coverage',
        ownedBy: 'participation',
        reason:
          'dashboard_overview 的 service_coverage 與 analyses/participation.json 重複，' +
          '本次以 participation 為單一來源。',
      },
      {
        path: 'annual.budget_trend',
        ownedBy: 'participation',
        reason: 'dashboard_overview 的 annual.budget_trend 與 participation 的 budget.trend 重複。',
      },
      {
        path: 'annual.budget_execution',
        ownedBy: 'participation',
        reason: 'dashboard_overview 的 annual.budget_execution 與 participation 的 budget.execution 重複。',
      },
      {
        // dashboard 的 annual.fertility 與 analyses/fertility.json 的 annual 是
        // 同一組資料，只差欄位命名（births_mother_age_18_35 vs totalBirths）。
        // fertility.json 的版本多了 youthRatio，資訊較完整，所以由它當來源。
        path: 'annual.fertility',
        ownedBy: 'fertility',
        reason:
          'dashboard_overview 的 annual.fertility 與 analyses/fertility.json 的 annual 是同一組年度生育資料' +
          '（欄位命名不同），以 fertility 分析為單一來源。',
      },
    ],
  },
  participation: {
    skipPaths: ['topics', 'elections.youth_candidacy.city_councilor_t1'],
    skipReasons: {
      topics:
        'participation 的 topics 子樹與 analyses/topic_weight.json、analyses/keyword_frequency.json ' +
        '兩個獨立 artifact 重複，本次以獨立 artifact 為單一來源。',
      'elections.youth_candidacy.city_councilor_t1':
        '市議員選舉的 31 筆資料是「選區」層級（新北市第01選區…），與本專案其他所有指標的' +
        '「29 個行政區」層級不對應，無法和同一區的其他資料互相參照；因此未納入 evidence。' +
        '全市合計的 city_councilor_t1_citywide 有納入，青年參選相關問題請以全市層級解讀。',
    },
    // borough_chief_v1 是 29 區 × 3 屆 = 87 筆，全部保留才能看趨勢。
    rowLimits: { 'elections.youth_candidacy.borough_chief_v1': 120 },
  },
  fertility: {
    // annual 是 5 年 × 29 區，district 篩選後只剩 5 筆，不需要額外限制。
    skipPaths: ['fafi.districts', 'daycareCoverage.districts.value'],
    skipReasons: {
      'fafi.districts':
        'fafi.districts 逐區的五個分數與 districts[] 上的 fafiScore / housingScore / wageScore / ' +
        'daycareCoverageScore / fafiLevel 是同一組值，只是換一種排列；以 districts[] 為單一來源。',
      'daycareCoverage.districts.value':
        'daycareCoverage.districts[].value 與 districts[].daycareCoverage 是同一個值；' +
        '以 districts[] 為單一來源（母體欄位 covered_population / target_population 仍保留）。',
    },
    dedupe: [
      {
        path: 'districts.opportunityIndex',
        ownedBy: 'dashboard_overview',
        reason: 'opportunityIndex 以 dashboard_overview 為單一來源。',
      },
      {
        path: 'districts.fertilityRate',
        ownedBy: 'dashboard_overview',
        reason: 'districts[].fertilityRate 以 dashboard_overview 為單一來源。',
      },
      {
        path: 'districts.score_housing',
        ownedBy: 'dashboard_overview',
        reason: 'score_housing 與 dashboard_overview 的 yoiComponents.housing 是同一個值。',
      },
      {
        path: 'districts.estimatedWage',
        ownedBy: 'employment',
        reason: 'estimatedWage 與 employment 的 estimated_wage 是同一個值。',
      },
    ],
  },
  employment: {
    dedupe: [
      {
        path: 'districts.opportunityIndex',
        ownedBy: 'dashboard_overview',
        reason: 'opportunityIndex 以 dashboard_overview 為單一來源。',
      },
      {
        path: 'districts.retentionRiskLevel',
        ownedBy: 'dashboard_overview',
        reason: 'retentionRiskLevel 以 dashboard_overview 為單一來源。',
      },
      // yoiComponents 與 score_* 在 employment 裡是**同一組數字的兩種命名**
      // （實測 score_job === yoiComponents.job），而 dashboard_overview 已經有
      // yoiComponents。三份同樣的五個分數會讓模型以為有三組獨立證據。
      {
        path: 'districts.yoiComponents',
        ownedBy: 'dashboard_overview',
        reason: 'yoiComponents 五個子分數以 dashboard_overview 為單一來源。',
      },
      {
        path: 'districts.score_job',
        ownedBy: 'dashboard_overview',
        reason: 'score_job 與 dashboard_overview 的 yoiComponents.job 是同一個值。',
      },
      {
        path: 'districts.score_salary',
        ownedBy: 'dashboard_overview',
        reason: 'score_salary 與 dashboard_overview 的 yoiComponents.salary 是同一個值。',
      },
      {
        path: 'districts.score_talent',
        ownedBy: 'dashboard_overview',
        reason: 'score_talent 與 dashboard_overview 的 yoiComponents.talent 是同一個值。',
      },
      {
        path: 'districts.score_housing',
        ownedBy: 'dashboard_overview',
        reason: 'score_housing 與 dashboard_overview 的 yoiComponents.housing 是同一個值。',
      },
      {
        path: 'districts.score_transport',
        ownedBy: 'dashboard_overview',
        reason: 'score_transport 與 dashboard_overview 的 yoiComponents.transport 是同一個值。',
      },
    ],
  },
  policy_support: {},
  topic_weight: {
    // 22 個議題 × 7 年 = 154 筆，但議題權重是「當前關注焦點」的呈現，
    // 跨年比較需要的是趨勢圖而不是 evidence 清單；只取最新一年並限制筆數。
    latestYearOnly: ['years'],
    fieldAllowlist: { 'years.topics': ['weight', 'join_mentions', 'minutes_mentions'] },
    rowLimits: { 'years.topics': 22 },
  },
  keyword_frequency: {
    // 每年 100 個關鍵詞 × 7 年 = 700 筆 × 每筆十幾個欄位，全放進 prompt 會直接爆掉，
    // 而且長尾關鍵詞（出現 1 次）沒有政策解讀價值。只取最新一年前 25 名的權重。
    latestYearOnly: ['years'],
    fieldAllowlist: { 'years.keywords': ['weight', 'term_frequency', 'document_count'] },
    rowLimits: { 'years.keywords': 25 },
  },
};

interface MetricMeta {
  unit: string | null;
  youthEligibility: YouthEligibility;
  ageScope: AgeScope;
}

/**
 * 指標的單位與青年適用性。key 是**葉欄位名稱**。
 *
 * 單位來自 `api_contract.md` §3.1 的單位表（那是 backend / frontend 已經對齊過的
 * 權威定義），不是我猜的。單位很重要 —— 實測發現過模型把 `TWD_thousand`
 * 的 220,101 講成「2 億 2,010 萬千元」，沒有單位標注就會出現這種錯。
 *
 * `youthEligibility` 的判斷原則：**不確定就往保守的方向標**。
 * `context_only` 的意思是「不可當青年專屬數據解讀」，把一個其實是青年指標的東西
 * 標成 context_only，代價是分析變保守；反過來把全年齡指標標成 eligible，
 * 代價是 AI 拿它當青年數據講 —— 後者是實質錯誤，前者只是保守。
 */
export const ANALYTICS_METRIC_META: Readonly<Record<string, MetricMeta>> = {
  // --- 人口 ---
  youth_18_35_total: { unit: '人', youthEligibility: 'eligible', ageScope: 'derived_18_35' },
  cityYouthPopulation: { unit: '人', youthEligibility: 'eligible', ageScope: 'derived_18_35' },
  cityYouthPopulationShare: { unit: '%', youthEligibility: 'eligible', ageScope: 'derived_18_35' },
  cityYouthPopulationYoY: { unit: '%', youthEligibility: 'eligible', ageScope: 'derived_18_35' },
  // 全國值由 data-pipeline 的 national_population（ODRP014 全國村里 18–35 歲加總）計算，
  // 口徑與 cityYouthPopulation 相同。只有該資料缺漏時 homepage 才退回常數並標
  // kpis.nationalYouthPopulationQuality = 'proxy'，那時要以該欄位為準。
  nationalYouthPopulation: { unit: '人', youthEligibility: 'eligible', ageScope: 'derived_18_35' },
  youth_population_18_35: { unit: '人', youthEligibility: 'eligible', ageScope: 'derived_18_35' },

  // --- 就業機會（api_contract.md §3.1 單位表）---
  vacancies_per_10k_youth: {
    unit: '職缺/萬青年',
    youthEligibility: 'eligible',
    ageScope: 'derived_18_35',
  },
  occupation_shannon_index: {
    unit: null,
    youthEligibility: 'context_only',
    ageScope: 'not_age_specific',
  },
  talent_demand_yoy: { unit: '%', youthEligibility: 'context_only', ageScope: 'not_age_specific' },
  salary_median: { unit: 'TWD/月', youthEligibility: 'context_only', ageScope: 'not_age_specific' },
  high_salary_ratio: {
    unit: '比例(0-1)',
    youthEligibility: 'context_only',
    ageScope: 'not_age_specific',
  },
  adjusted_youth_wage: {
    unit: '萬元/年',
    youthEligibility: 'proxy_only',
    ageScope: 'official_age_group_proxy',
  },
  college_student_density: {
    unit: '人/km²',
    youthEligibility: 'context_only',
    ageScope: 'not_age_specific',
  },
  vt_course_count: { unit: '門', youthEligibility: 'context_only', ageScope: 'not_age_specific' },
  training_people_per_10k_youth: {
    unit: '人次/萬青年',
    youthEligibility: 'eligible',
    ageScope: 'derived_18_35',
  },
  knowledge_job_ratio: { unit: '%', youthEligibility: 'context_only', ageScope: 'not_age_specific' },
  estimated_wage: {
    unit: '萬元/年',
    youthEligibility: 'proxy_only',
    ageScope: 'official_age_group_proxy',
  },
  estimated_monthly_wage: {
    unit: '萬元/月',
    youthEligibility: 'proxy_only',
    ageScope: 'official_age_group_proxy',
  },
  estimatedWage: {
    unit: '萬元/年',
    youthEligibility: 'proxy_only',
    ageScope: 'official_age_group_proxy',
  },

  // --- 居住負擔 ---
  rent_median: { unit: 'TWD/月', youthEligibility: 'context_only', ageScope: 'not_age_specific' },
  house_price_median: {
    unit: 'TWD/坪',
    youthEligibility: 'context_only',
    ageScope: 'not_age_specific',
  },
  house_price_median_wan: {
    unit: '萬元/坪',
    youthEligibility: 'context_only',
    ageScope: 'not_age_specific',
  },
  rent_wage_ratio: { unit: '比例', youthEligibility: 'context_only', ageScope: 'not_age_specific' },

  // --- 交通 ---
  bus_stops_per_10k_youth: {
    unit: '站/萬青年',
    youthEligibility: 'eligible',
    ageScope: 'derived_18_35',
  },
  railway_stop_density: {
    unit: '站/km²',
    youthEligibility: 'context_only',
    ageScope: 'not_age_specific',
  },
  bike_stop_density: {
    unit: '站/km²',
    youthEligibility: 'context_only',
    ageScope: 'not_age_specific',
  },

  // --- 複合指數 ---
  opportunityIndex: { unit: '分(0-100)', youthEligibility: 'eligible', ageScope: 'derived_18_35' },
  job: { unit: '分(0-100)', youthEligibility: 'eligible', ageScope: 'derived_18_35' },
  salary: { unit: '分(0-100)', youthEligibility: 'eligible', ageScope: 'derived_18_35' },
  talent: { unit: '分(0-100)', youthEligibility: 'eligible', ageScope: 'derived_18_35' },
  housing: { unit: '分(0-100)', youthEligibility: 'eligible', ageScope: 'derived_18_35' },
  transport: { unit: '分(0-100)', youthEligibility: 'eligible', ageScope: 'derived_18_35' },
  score_job: { unit: '分(0-100)', youthEligibility: 'eligible', ageScope: 'derived_18_35' },
  score_salary: { unit: '分(0-100)', youthEligibility: 'eligible', ageScope: 'derived_18_35' },
  score_talent: { unit: '分(0-100)', youthEligibility: 'eligible', ageScope: 'derived_18_35' },
  score_housing: { unit: '分(0-100)', youthEligibility: 'eligible', ageScope: 'derived_18_35' },
  score_transport: { unit: '分(0-100)', youthEligibility: 'eligible', ageScope: 'derived_18_35' },
  retentionRiskLevel: { unit: null, youthEligibility: 'eligible', ageScope: 'derived_18_35' },

  // --- 生育 ---
  fertilityRate: { unit: '‰', youthEligibility: 'eligible', ageScope: 'derived_18_35' },
  fertilityVsCityAvg: { unit: '%', youthEligibility: 'eligible', ageScope: 'derived_18_35' },
  totalBirths: { unit: '人', youthEligibility: 'context_only', ageScope: 'not_age_specific' },
  youthRatio: { unit: '%', youthEligibility: 'eligible', ageScope: 'derived_18_35' },
  averageMonthlyFemale18_35: { unit: '人', youthEligibility: 'eligible', ageScope: 'derived_18_35' },
  daycareCoverage: { unit: '%', youthEligibility: 'eligible', ageScope: 'derived_18_35' },
  daycareCoverageScore: { unit: '分(0-100)', youthEligibility: 'eligible', ageScope: 'derived_18_35' },
  housingScore: { unit: '分(0-100)', youthEligibility: 'eligible', ageScope: 'derived_18_35' },
  wageScore: { unit: '分(0-100)', youthEligibility: 'eligible', ageScope: 'derived_18_35' },
  fafiScore: { unit: '分(0-100)', youthEligibility: 'eligible', ageScope: 'derived_18_35' },
  fafiLevel: { unit: null, youthEligibility: 'eligible', ageScope: 'derived_18_35' },
  fertilityLevel: { unit: null, youthEligibility: 'eligible', ageScope: 'derived_18_35' },

  // --- 青年參與 / 服務資源 ---
  youthParticipationIndex: { unit: null, youthEligibility: 'eligible', ageScope: 'derived_18_35' },
  // api_contract.md 明確警告：這個值的單位是「每十萬青年」，不是 %。
  youthCandidacyRatePer100k: {
    unit: '人/十萬青年',
    youthEligibility: 'eligible',
    ageScope: 'derived_18_35',
  },
  youth_candidacy_rate: {
    unit: '人/十萬青年',
    youthEligibility: 'eligible',
    ageScope: 'derived_18_35',
  },
  serviceCoverageRate: { unit: '%', youthEligibility: 'eligible', ageScope: 'derived_18_35' },
  service_coverage_rate: { unit: '%', youthEligibility: 'eligible', ageScope: 'derived_18_35' },

  // --- 預算 ---
  currentBudget: {
    unit: 'TWD_thousand',
    youthEligibility: 'context_only',
    ageScope: 'not_age_specific',
  },
  budgetYoY: { unit: '%', youthEligibility: 'context_only', ageScope: 'not_age_specific' },
  legal_budget_amount: {
    unit: 'TWD_thousand',
    youthEligibility: 'context_only',
    ageScope: 'not_age_specific',
  },
  budget_yoy_percent: { unit: '%', youthEligibility: 'context_only', ageScope: 'not_age_specific' },
  execution_rate: { unit: '%', youthEligibility: 'context_only', ageScope: 'not_age_specific' },
  amount_twd_thousand: {
    unit: 'TWD_thousand',
    youthEligibility: 'context_only',
    ageScope: 'not_age_specific',
  },
  value_thousand: {
    unit: 'TWD_thousand',
    youthEligibility: 'context_only',
    ageScope: 'not_age_specific',
  },

  // --- 施政成果趨勢 ---
  wage: {
    unit: '萬元/年',
    youthEligibility: 'proxy_only',
    ageScope: 'official_age_group_proxy',
  },
  population: { unit: '人', youthEligibility: 'eligible', ageScope: 'derived_18_35' },
  currentWageGrowth: { unit: '%', youthEligibility: 'proxy_only', ageScope: 'official_age_group_proxy' },
  currentPopGrowth: { unit: '%', youthEligibility: 'eligible', ageScope: 'derived_18_35' },
  yoy: { unit: '%', youthEligibility: 'context_only', ageScope: 'not_age_specific' },

  // --- 議題 / 關鍵詞 ---
  weight: { unit: '權重(0-1)', youthEligibility: 'context_only', ageScope: 'not_age_specific' },
  term_frequency: { unit: '次', youthEligibility: 'context_only', ageScope: 'not_age_specific' },
  document_count: { unit: '件', youthEligibility: 'context_only', ageScope: 'not_age_specific' },
  join_mentions: { unit: '次', youthEligibility: 'context_only', ageScope: 'not_age_specific' },
  minutes_mentions: { unit: '次', youthEligibility: 'context_only', ageScope: 'not_age_specific' },

  // --- 迴歸 ---
  slope: { unit: null, youthEligibility: 'context_only', ageScope: 'not_age_specific' },
  intercept: { unit: null, youthEligibility: 'context_only', ageScope: 'not_age_specific' },
  r_squared: { unit: null, youthEligibility: 'context_only', ageScope: 'not_age_specific' },
  sample_size: { unit: '筆', youthEligibility: 'context_only', ageScope: 'not_age_specific' },

  // ===========================================================================
  // 以下是用 `npm run dev:metric-audit` 對真實快照稽核後補的。
  //
  // 稽核方式是看**實際產生出來的 evidence**，不是數 JSON 葉欄位 ——
  // 後者會高估問題（villages / normalizedInputs / points / time_policy 早就被
  // BLOCKED_KEYS 擋掉）。補之前 215 種指標裡有 118 種沒有單位。
  // ===========================================================================

  // --- 年度人口（annual.population.*）---
  people_total: { unit: '人', youthEligibility: 'context_only', ageScope: 'all_ages' },
  youth_share_percent: { unit: '%', youthEligibility: 'eligible', ageScope: 'derived_18_35' },
  yoy_percent: { unit: '%', youthEligibility: 'context_only', ageScope: 'not_age_specific' },
  youth_ratio: { unit: '%', youthEligibility: 'eligible', ageScope: 'derived_18_35' },
  youth_yoy: { unit: '%', youthEligibility: 'eligible', ageScope: 'derived_18_35' },

  // --- 資料完整度（保留但標明單位）---
  // 這幾個不像 coverage 容器那樣純屬管線內部：availableMonths=9 的意思是
  // 「這個年度值只用了 9 個月的資料」，使用者解讀年度數字時需要知道。
  availableMonths: { unit: '月', youthEligibility: 'context_only', ageScope: 'not_age_specific' },
  available_months: { unit: '月', youthEligibility: 'context_only', ageScope: 'not_age_specific' },
  coverageRatio: { unit: '比例', youthEligibility: 'context_only', ageScope: 'not_age_specific' },
  coverage_ratio: { unit: '比例', youthEligibility: 'context_only', ageScope: 'not_age_specific' },
  qualityStatus: { unit: null, youthEligibility: 'context_only', ageScope: 'not_age_specific' },
  serviceCoverageStatus: {
    unit: null,
    youthEligibility: 'context_only',
    ageScope: 'not_age_specific',
  },
  daycareCoverageStatus: {
    unit: null,
    youthEligibility: 'context_only',
    ageScope: 'not_age_specific',
  },

  // --- 就業補充指標 ---
  vacancies_per_km2: {
    unit: '職缺/平方公里',
    youthEligibility: 'context_only',
    ageScope: 'not_age_specific',
  },
  salary_sample_size: { unit: '筆', youthEligibility: 'context_only', ageScope: 'not_age_specific' },
  salarySampleSize: { unit: '筆', youthEligibility: 'context_only', ageScope: 'not_age_specific' },
  // shrunk 是做過收縮估計的中位數（小樣本往全市平均拉），跟原始中位數不同，
  // 但單位一樣。兩者同時出現時模型要能看出是「兩個算法」而不是「兩期資料」。
  salary_median_shrunk: {
    unit: 'TWD/月',
    youthEligibility: 'context_only',
    ageScope: 'not_age_specific',
  },
  salaryMedian: { unit: 'TWD/月', youthEligibility: 'context_only', ageScope: 'not_age_specific' },
  yoiRaw: { unit: '分(0-100)', youthEligibility: 'eligible', ageScope: 'derived_18_35' },

  // --- 服務／托育涵蓋 ---
  // `value` 是 service_coverage 與 daycareCoverage 共用的葉名，兩者都是百分比。
  // 對照表的 key 是葉名，沒辦法分辨是哪一個，所以 youthEligibility 取保守的
  // context_only —— service_coverage 其實是青年專屬，標保守只會讓分析謹慎，
  // 反過來把托育涵蓋標成青年數據才是實質錯誤。
  value: { unit: '%', youthEligibility: 'context_only', ageScope: 'not_age_specific' },
  target_population: { unit: '人', youthEligibility: 'context_only', ageScope: 'not_age_specific' },
  covered_population: {
    unit: '人',
    youthEligibility: 'context_only',
    ageScope: 'not_age_specific',
  },
  covered_youth: { unit: '人', youthEligibility: 'eligible', ageScope: 'derived_18_35' },
  youth_population: { unit: '人', youthEligibility: 'eligible', ageScope: 'derived_18_35' },
  village_count: { unit: '里', youthEligibility: 'context_only', ageScope: 'not_age_specific' },
  covered_village_count: {
    unit: '里',
    youthEligibility: 'context_only',
    ageScope: 'not_age_specific',
  },

  // --- 生育（年度）---
  births_mother_age_18_35: { unit: '人', youthEligibility: 'eligible', ageScope: 'derived_18_35' },
  average_monthly_female_18_35: {
    unit: '人',
    youthEligibility: 'eligible',
    ageScope: 'derived_18_35',
  },
  fertility_rate: { unit: '‰', youthEligibility: 'eligible', ageScope: 'derived_18_35' },

  // --- 選舉／青年參政 ---
  candidate_count: { unit: '人', youthEligibility: 'context_only', ageScope: 'all_ages' },
  age_known_candidate_count: {
    unit: '人',
    youthEligibility: 'context_only',
    ageScope: 'all_ages',
  },
  youth_candidate_count: { unit: '人', youthEligibility: 'eligible', ageScope: 'derived_18_35' },
  elected_count: { unit: '人', youthEligibility: 'context_only', ageScope: 'all_ages' },
  youth_elected_count: { unit: '人', youthEligibility: 'eligible', ageScope: 'derived_18_35' },
  elected_seat_count: { unit: '席', youthEligibility: 'context_only', ageScope: 'not_age_specific' },
  // 實測值 0.8：125 席里 1 席是青年 → 1/125 = 0.008 → 0.8%。是百分比不是比例。
  youth_borough_chief_ratio: {
    unit: '%',
    youthEligibility: 'eligible',
    ageScope: 'derived_18_35',
  },
  population_total: { unit: '人', youthEligibility: 'context_only', ageScope: 'all_ages' },
  youth_population_share: { unit: '%', youthEligibility: 'eligible', ageScope: 'derived_18_35' },
  // yrr = youth representation ratio：青年當選比 ÷ 青年人口比。
  // 實測 0.029102 ≈ 0.008 / 0.2749，所以是**比例**（1 代表席次與人口比相符）。
  yrr: { unit: '比例', youthEligibility: 'eligible', ageScope: 'derived_18_35' },
  latest_v1_youth_elected_count: {
    unit: '人',
    youthEligibility: 'eligible',
    ageScope: 'derived_18_35',
  },
  latest_v1_elected_seat_count: {
    unit: '席',
    youthEligibility: 'context_only',
    ageScope: 'not_age_specific',
  },

  // --- 預算 ---
  // ⚠️ 單位不一致，這是實測踩過的坑（把 220,101 千元講成「2 億 2,010 萬千元」）。
  // legal_budget_amount_for_execution 實測 149,029，而同一組的 realized_amount
  // 是 138,627,956 —— 兩者相差三個位數，所以前者是**千元**、後者是**元**。
  legal_budget_amount_for_execution: {
    unit: 'TWD_thousand',
    youthEligibility: 'context_only',
    ageScope: 'not_age_specific',
  },
  realized_amount: { unit: 'TWD', youthEligibility: 'context_only', ageScope: 'not_age_specific' },
  settlement_amount: { unit: 'TWD', youthEligibility: 'context_only', ageScope: 'not_age_specific' },
  payable_amount: { unit: 'TWD', youthEligibility: 'context_only', ageScope: 'not_age_specific' },
  reserved_amount: { unit: 'TWD', youthEligibility: 'context_only', ageScope: 'not_age_specific' },
  surplus_amount: { unit: 'TWD', youthEligibility: 'context_only', ageScope: 'not_age_specific' },
  amount: { unit: 'TWD', youthEligibility: 'context_only', ageScope: 'not_age_specific' },
  total_amount: { unit: 'TWD', youthEligibility: 'context_only', ageScope: 'not_age_specific' },
  share_percent: { unit: '%', youthEligibility: 'context_only', ageScope: 'not_age_specific' },

  // --- 提案漏斗 ---
  count: { unit: '件', youthEligibility: 'context_only', ageScope: 'not_age_specific' },
  escalated_to_council: {
    unit: '件',
    youthEligibility: 'context_only',
    ageScope: 'not_age_specific',
  },
};

/**
 * 名稱規則的 fallback。表裡查不到時用這個，仍然比一律 null 誠實。
 * 只做「往 eligible 靠」的判斷，因為那需要名稱明確帶有青年口徑。
 */
function inferMeta(leafKey: string): MetricMeta {
  const known = ANALYTICS_METRIC_META[leafKey];
  if (known) {
    return known;
  }
  const lower = leafKey.toLowerCase();
  if (lower.includes('youth') || lower.includes('18_35') || lower.includes('per_10k_youth')) {
    return { unit: null, youthEligibility: 'eligible', ageScope: 'derived_18_35' };
  }
  // 查不到就保守標 context_only：寧可讓分析變保守，也不要讓全年齡指標被當成青年數據。
  return { unit: null, youthEligibility: 'context_only', ageScope: 'not_age_specific' };
}

/**
 * 路徑前綴 → geoLevel。
 *
 * 沒有 district 的資料不代表就是「全市」：青年局預算、補助、提案追蹤都是**機關**
 * 層級。標成 county 會讓模型把青年局的預算講成「新北市的青年預算」，那是不同的東西。
 */
const GEO_LEVEL_BY_PATH_PREFIX: readonly { prefix: string; geoLevel: GeoLevel }[] = [
  { prefix: 'policy', geoLevel: 'organization' },
  { prefix: 'budget', geoLevel: 'organization' },
  { prefix: 'grants', geoLevel: 'organization' },
  { prefix: 'proposal_funnel', geoLevel: 'organization' },
  { prefix: 'overview', geoLevel: 'county' },
];

export interface FlattenAnalyticsOptions {
  /** manifest 的 artifact key，例如 `employment` */
  artifactKey: string;
  /** 相對 dataDir 的路徑，成為 evidence 的 sourcePath */
  sourcePath: string;
  snapshotId: string;
  /** manifest 的 generated_at，成為 evidence 的 fetchedAt */
  generatedAt: string | null;
  /** 上游 curated dataset 名稱，寫進 computation */
  upstreamDatasets: readonly string[];
  /** 這個快照裡有哪些 artifact key，決定 dedupe 規則要不要生效 */
  availableArtifactKeys: readonly string[];
}

export interface FlattenAnalyticsResult {
  evidence: AiEvidence[];
  /** pipeline 自己宣告的品質限制，必須進到輸出的 limitations */
  notes: string[];
}

interface WalkContext {
  /** 不含陣列索引與行政區 key 的邏輯路徑 */
  logicalPath: string;
  /** metricId 用的路徑（已去掉結構性容器名稱） */
  metricPath: string;
  districtId: string | null;
  districtName: string | null;
  period: string | null;
  periodType: PeriodType | null;
  rowLabel: string | null;
}

/**
 * 攤平一個 artifact。
 */
export function flattenAnalyticsArtifact(
  payload: unknown,
  options: FlattenAnalyticsOptions,
): FlattenAnalyticsResult {
  const dataset = analyticsDatasetName(options.artifactKey);
  const rule = ANALYTICS_ARTIFACT_RULES[options.artifactKey] ?? {};
  const evidence: AiEvidence[] = [];
  const notes = new Set<string>();
  const usedEvidenceIds = new Set<string>();

  // 這個 artifact 的 calculation_version 要寫進 computation，讓結論可以綁到具體版本。
  const calculationVersion =
    payload !== null && typeof payload === 'object' && !Array.isArray(payload)
      ? asString((payload as Record<string, unknown>).calculation_version)
      : null;

  const skipPaths = new Set(rule.skipPaths ?? []);
  for (const dedupe of rule.dedupe ?? []) {
    if (options.availableArtifactKeys.includes(dedupe.ownedBy)) {
      skipPaths.add(dedupe.path);
      notes.add(dedupe.reason);
    }
  }
  for (const skipped of rule.skipPaths ?? []) {
    const reason = rule.skipReasons?.[skipped];
    if (reason) {
      notes.add(reason);
    }
  }

  // 行政區代碼 ↔ 中文名稱的對照，從這個 artifact 自己的內容建立。
  // 需要它的原因：有些區塊只帶代碼（`fafi.districts` 的 key）或只帶名稱，
  // 而 `applyEvidenceFilters()` 是用「名稱或代碼任一符合」來篩選 —— 少一邊，
  // 使用者選了「板橋區」時那些只有代碼的指標就會整批消失。
  const districtIndex = buildDistrictIndex(payload);

  const emit = (context: WalkContext, leafKey: string, value: number | string): void => {
    if (evidence.length >= MAX_EVIDENCE_PER_ARTIFACT) {
      return;
    }
    const meta = inferMeta(leafKey);
    const metricId = buildMetricId(context, leafKey);
    const period = context.period ?? `snapshot:${options.snapshotId}`;
    const districtId =
      context.districtId ??
      (context.districtName !== null ? districtIndex.idByName.get(context.districtName) ?? null : null);
    const districtName =
      context.districtName ??
      (context.districtId !== null ? districtIndex.nameById.get(context.districtId) ?? null : null);
    const geoLevel = resolveGeoLevel(context, leafKey);
    evidence.push({
      evidenceId: buildAnalyticsEvidenceId(usedEvidenceIds, {
        dataset,
        period,
        // 用 prompt 上顯示的同一個 scope 字串，模型才有辦法自己重組出這個 id。
        scope: evidenceScopeLabel(districtName, geoLevel),
        metricId,
      }),
      dataset,
      source: ANALYTICS_SOURCE_ID,
      sourceRecordId: null,
      sourceUrl: null,
      sourceKind: 'dataset',
      geoLevel,
      districtId,
      districtName,
      period,
      // analytics 的 artifact 不提供逐指標的起訖日期，只有期間標籤（year_roc）
      // 或「最新可得快照」。硬填一個日期區間會是編造的。
      periodStart: null,
      periodEnd: null,
      periodType: context.periodType ?? (context.period === null ? 'snapshot' : null),
      metricId,
      metricSource: 'analytics_metric',
      value,
      unit: meta.unit,
      computation: buildComputation(options, calculationVersion, context, leafKey),
      ageScope: meta.ageScope,
      youthEligibility: meta.youthEligibility,
      // 品質旗標在 analytics 是分析層級的 status / blocking_reasons，
      // 不是逐筆的旗標，所以走 notes 而不是塞進每一筆。
      qualityFlags: [],
      sourcePath: options.sourcePath,
      fetchedAt: options.generatedAt,
    });
  };

  walk(payload, {
    logicalPath: '',
    metricPath: '',
    districtId: null,
    districtName: null,
    period: null,
    periodType: null,
    rowLabel: null,
  });

  return { evidence, notes: [...notes] };

  function walk(node: unknown, context: WalkContext): void {
    if (node === null || node === undefined) {
      return;
    }

    if (Array.isArray(node)) {
      walkArray(node, context);
      return;
    }

    if (typeof node !== 'object') {
      return;
    }

    walkObject(node as Record<string, unknown>, context);
  }

  function walkArray(node: readonly unknown[], context: WalkContext): void {
    const limit = rule.rowLimits?.[context.logicalPath] ?? DEFAULT_ROW_LIMIT;
    let rows = node;

    // `latestYearOnly`：只留 year_roc 最大的那一筆。用在議題與關鍵詞這種
    // 「當前焦點」型的資料上，跨年全撈進來只會讓 prompt 爆掉又不好解讀。
    if (rule.latestYearOnly?.includes(context.logicalPath)) {
      const latest = pickLatestYearRow(node);
      if (latest !== null) {
        rows = [latest];
        notes.add(
          `${options.artifactKey} 的 ${context.logicalPath} 只取最新一期（${asString(latest.year_roc) ?? String(latest.year_roc)} 年），` +
            '歷年趨勢未納入本次 evidence。',
        );
      }
    }

    if (rows.length > limit) {
      notes.add(
        `${options.artifactKey} 的 ${context.logicalPath} 共 ${rows.length} 筆，僅取前 ${limit} 筆進 evidence；` +
          '這是為了控制 prompt 長度而截斷，不可據此推論全體分布。',
      );
      rows = rows.slice(0, limit);
    }

    for (const item of rows) {
      walk(item, context);
    }
  }

  function walkObject(node: Record<string, unknown>, context: WalkContext): void {
    // 這一層先把「維度」讀出來：行政區、期間、列標籤。這些會傳給同層的數值欄位。
    const childContext: WalkContext = {
      ...context,
      districtId: asString(node.district_id) ?? context.districtId,
      districtName: asString(node.district_name) ?? context.districtName,
      rowLabel: pickRowLabel(node) ?? context.rowLabel,
    };

    const year = pickYear(node);
    if (year !== null) {
      childContext.period = year;
      childContext.periodType = 'year';
    }

    const allowlist = rule.fieldAllowlist?.[context.logicalPath];

    for (const [key, value] of Object.entries(node)) {
      if (BLOCKED_KEYS.has(key)) {
        continue;
      }

      const nextLogicalPath = context.logicalPath === '' ? key : `${context.logicalPath}.${key}`;
      if (isSkipped(nextLogicalPath)) {
        continue;
      }

      if (NOTE_KEYS.has(key)) {
        collectNotes(key, value, childContext);
        continue;
      }

      if (METADATA_KEYS.has(key)) {
        continue;
      }

      // 物件與陣列往下走；巢狀的 key 會累積進 metricId，所以
      // `scatter.knowledge_job_vs_estimated_wage.regression.slope` 讀起來仍然明確。
      if (value !== null && typeof value === 'object') {
        // 「key 本身就是行政區代碼」的形狀：實測 fertility 的 `fafi.districts` 是
        // `{ "65000010": { fafiScore… }, … }`，行政區只存在於 key 上，物件裡面
        // 沒有 district_id 欄位。不處理的話這些分數會全部變成「全市層級」，
        // 而且會被行政區篩選整批濾掉。
        const districtIdFromKey = isDistrictIdKey(key) ? key : null;
        walk(value, {
          ...childContext,
          districtId: districtIdFromKey ?? childContext.districtId,
          // logicalPath 刻意不含行政區代碼：否則 rowLimits / skipPaths 這些
          // 以路徑為 key 的規則，會需要為 29 個代碼各寫一條。
          logicalPath: districtIdFromKey === null ? nextLogicalPath : context.logicalPath,
          metricPath: extendMetricPath(childContext.metricPath, key),
        });
        continue;
      }

      if (allowlist !== undefined && !allowlist.includes(key)) {
        continue;
      }

      // 布林值不產生 evidence：`resolved: true` 這種是流程狀態，
      // 當成數值引用只會讓模型寫出「resolved = 1」這種無意義的句子。
      if (typeof value === 'boolean') {
        continue;
      }
      if (typeof value === 'number' && Number.isFinite(value)) {
        emit(childContext, key, value);
        continue;
      }
      if (typeof value === 'string' && LEVEL_VALUE_KEYS.has(key)) {
        emit(childContext, key, value);
      }
    }
  }

  /**
   * 處理「物件的 key 是行政區代碼」這種形狀。
   * 實測 fertility 的 `fafi.districts` 就是 `{ "65000010": {...}, ... }`。
   */
  function isSkipped(logicalPath: string): boolean {
    for (const skipped of skipPaths) {
      if (logicalPath === skipped || logicalPath.startsWith(`${skipped}.`)) {
        return true;
      }
    }
    return false;
  }

  function collectNotes(key: string, value: unknown, context: WalkContext): void {
    const scope = context.districtName ? `${context.districtName}的` : '';
    const where = context.logicalPath === '' ? options.artifactKey : `${options.artifactKey}.${context.logicalPath}`;

    if (typeof value === 'string') {
      if (key === 'status' || key === 'quality_status' || key === 'budget_status') {
        // observed 是正常狀態，不需要在每個回應裡都講一遍。
        if (value !== 'observed' && value !== 'available') {
          notes.add(`${where} 的資料狀態是 ${value}（非 observed），${scope}相關數字解讀時必須保留。`);
        }
        return;
      }
      notes.add(`${where} 標示 ${key}=${value}。`);
      return;
    }

    if (Array.isArray(value)) {
      for (const item of value) {
        if (typeof item === 'string') {
          notes.add(`${where} 的 ${key}：${item}。`);
        } else if (item !== null && typeof item === 'object') {
          const record = item as Record<string, unknown>;
          const metric = asString(record.metric);
          const reason = asString(record.reason);
          notes.add(
            `${where} 的 ${key}：${[metric, reason].filter((part) => part !== null).join(' — ') || JSON.stringify(record)}。`,
          );
        }
      }
      return;
    }

    // `availability: { opportunityIndex: 'available', budget: 'partial' }`
    if (value !== null && typeof value === 'object') {
      for (const [subject, state] of Object.entries(value as Record<string, unknown>)) {
        if (typeof state === 'string' && state !== 'available' && state !== 'observed') {
          notes.add(`${where} 宣告 ${subject} 的資料可用性是 ${state}，該面向的結論必須標明資料不完整。`);
        }
      }
    }
  }
}

/**
 * 跨 artifact 的重複值收合。
 *
 * 上面 `ANALYTICS_ARTIFACT_RULES` 的 dedupe 是逐條列舉的、精確的；這個函式是
 * **後備網**，處理沒被列舉到的重複。
 *
 * 為什麼需要後備網：analytics 的 6 個 analysis artifact 之間本來就會互相引用彼此的
 * 指標（employment 要 house_price 才能算居住分數、fertility 要 opportunityIndex 才能
 * 畫散佈圖），所以同一個數字出現在多個 artifact 是常態，而且 pipeline 每加一個
 * 分析就可能多一組重複。逐條列舉追不上。
 *
 * 為什麼重複必須收掉：模型會把「兩個不同 evidenceId 有同樣的數字」當成兩個獨立
 * 來源互相佐證。那是憑空生出來的可信度 —— 實際上只有一個來源。
 *
 * 收合的判斷是**同一個行政區、同一期間、同一單位、同一個值、指標名的最後一段相同**。
 * 保留第一筆（manifest 順序，dashboard_overview 在前），因為那是最「正式」的呈現位置。
 *
 * 刻意**不**只用值比對：不同指標偶然數值相同是可能的（例如兩個都是 12 個月），
 * 加上指標名最後一段可以避免把不同的東西合掉。
 */
export function dedupeAnalyticsEvidence(evidence: readonly AiEvidence[]): {
  evidence: AiEvidence[];
  removed: number;
} {
  const seen = new Set<string>();
  const kept: AiEvidence[] = [];
  for (const item of evidence) {
    const leaf = item.metricId.split('.').pop() ?? item.metricId;
    const scope = item.districtId ?? item.districtName ?? item.geoLevel ?? '';
    const key = [scope, item.period, item.unit ?? '', String(item.value), leaf].join('|');
    if (seen.has(key)) {
      continue;
    }
    seen.add(key);
    kept.push(item);
  }
  return { evidence: kept, removed: evidence.length - kept.length };
}

/**
 * evidenceId 格式：`{dataset}:{period}:{scope}:{metricId}`。
 *
 * ## 為什麼不用流水號
 *
 * 第一版是 `{dataset}:{period}:{流水號}:{metricId}`（照 curated 的格式）。
 * 真模型實測直接踩雷：Policy Copilot 引用了
 * `analytics_dashboard_overview:snapshot:dev-full-20260912:2:kpis.cityYouthPopulationYoY`，
 * 但那個指標的流水號是 3 不是 2 —— **指標名是對的，流水號差一。**
 * 於是 `runFeature()` 判定「引用了不存在的 evidenceId」，整個回應被拒絕。
 *
 * 問題在於流水號對模型沒有任何意義：它是走訪順序的副產品，模型無法推導、
 * 只能一字一字照抄一長串不透明的字串，抄錯一位整份分析就作廢。
 *
 * curated 那邊用流水號是合理的，因為它是**記錄在檔案裡的第幾筆**，人可以拿它回頭定位。
 * analytics 的走訪順序沒有這種意義。
 *
 * 換成「資料集 + 期間 + 範圍 + 指標名」之後，每一個組成部分都直接出現在
 * prompt 的 evidence 清單上（dataset=、period=、scope=、metric=），模型是在
 * **重組看得見的欄位**而不是背一個編號。
 *
 * 唯一性：`metricId` 已經含完整路徑與列標籤，加上範圍與期間之後實測不會重複。
 * 但不能只靠「實測不會」—— 萬一重複，兩筆 evidence 會共用同一個 id，引用就變得
 * 無法分辨。所以真的碰撞時補一個 `~n` 後綴，而且因為走訪順序是決定性的，
 * 同樣的輸入永遠得到同樣的 id。
 */
export function buildAnalyticsEvidenceId(
  used: Set<string>,
  parts: { dataset: string; period: string; scope: string; metricId: string },
): string {
  const base = `${parts.dataset}:${parts.period}:${parts.scope}:${parts.metricId}`;
  if (!used.has(base)) {
    used.add(base);
    return base;
  }
  let suffix = 2;
  while (used.has(`${base}~${suffix}`)) {
    suffix += 1;
  }
  const unique = `${base}~${suffix}`;
  used.add(unique);
  return unique;
}

/**
 * metricId：`<metricPath>.<leafKey>`，有列標籤時再加 `#<標籤>`。
 *
 * 例：
 * - `districts[].opportunityIndex` → `opportunityIndex`
 * - `annual.fertility.years[].districts[].fertilityRate` → `annual.fertility.fertilityRate`
 * - `scatter.x.regression.slope` → `scatter.<圖名>.regression.slope`
 * - `years[].keywords[].weight`（term=居住正義）→ `keywords.weight#居住正義`
 */
function buildMetricId(context: WalkContext, leafKey: string): string {
  const base = context.metricPath === '' ? leafKey : `${context.metricPath}.${leafKey}`;
  return context.rowLabel === null ? base : `${base}#${context.rowLabel}`;
}

function extendMetricPath(metricPath: string, key: string): string {
  if (STRUCTURAL_PATH_KEYS.has(key) || isDistrictIdKey(key)) {
    return metricPath;
  }
  return metricPath === '' ? key : `${metricPath}.${key}`;
}

function resolveGeoLevel(context: WalkContext, leafKey: string): GeoLevel {
  if (context.districtId !== null || context.districtName !== null) {
    return 'district';
  }
  if (leafKey.startsWith('national')) {
    return 'national';
  }
  const root = context.logicalPath.split('.')[0] ?? '';
  const match = GEO_LEVEL_BY_PATH_PREFIX.find((item) => item.prefix === root);
  if (match) {
    return match.geoLevel;
  }
  // 剩下的是全市層級（新北市）。用 county 而不是 national ——
  // 這個專案的全域範圍是新北市，不是全國。
  return 'county';
}

/**
 * `computation`：這個數字是誰算的、哪個版本、上游是什麼。
 *
 * 複合指標沒有這段就是黑箱，`basis` 的 note 也沒辦法交代「這個中位數怎麼來的」。
 */
function buildComputation(
  options: FlattenAnalyticsOptions,
  calculationVersion: string | null,
  context: WalkContext,
  leafKey: string,
): string {
  const location = context.logicalPath === '' ? leafKey : `${context.logicalPath}.${leafKey}`;
  const version = calculationVersion === null ? '' : ` v${calculationVersion}`;
  // 刻意**不**放上游 dataset 清單：那份清單是整個快照共用的常數，放進每一筆
  // evidence 等於在 prompt 裡重複幾百次同樣的字串（實測一個行政區 477 筆
  // evidence，光這一段就多 4 萬字元）。它改成由 snapshot 層級的 note 講一次，
  // 見 `analyticsSnapshotNote()`。
  return `analytics:${options.artifactKey}.${location} @${options.snapshotId}${version}`;
}

/**
 * 整個快照講一次就夠的來源說明。
 *
 * 這裡放的是所有 analytics evidence 共用的資訊：這些數字不是官方發布的統計、
 * 是本專案用哪些公開資料算出來的、算的時間點。每一筆 evidence 的 `computation`
 * 只放它自己獨有的位置與版本。
 */
export function analyticsSnapshotNote(
  snapshotId: string,
  generatedAt: string | null,
  upstreamDatasets: readonly string[],
): string {
  const when = generatedAt === null ? '' : `，計算時間 ${generatedAt}`;
  const upstream =
    upstreamDatasets.length === 0 ? '' : `，上游資料集：${upstreamDatasets.join('、')}`;
  return (
    `本次回應中 metricSource=analytics_metric 的指標，全部來自本專案資料管線的 ` +
    `Deterministic Analytics 快照 ${snapshotId}${when}${upstream}。` +
    '這些是以政府公開資料計算出來的彙總指標，**不是任何機關發布的官方統計數字**，' +
    '引用時不可標示為某個機關的官方數據；每一筆的計算位置記在該筆的 computation 欄位。'
  );
}

function pickRowLabel(node: Record<string, unknown>): string | null {
  for (const key of ROW_LABEL_KEYS) {
    const value = asString(node[key]);
    if (value !== null) {
      return value;
    }
  }
  return null;
}

/** 期間：year_roc 優先，其次 election_year_roc（選舉屆別年）。 */
function pickYear(node: Record<string, unknown>): string | null {
  for (const key of ['year_roc', 'election_year_roc']) {
    const value = node[key];
    if (typeof value === 'number' && Number.isFinite(value)) {
      return String(value);
    }
    const asText = asString(value);
    if (asText !== null) {
      return asText;
    }
  }
  return null;
}

function pickLatestYearRow(rows: readonly unknown[]): Record<string, unknown> | null {
  let best: Record<string, unknown> | null = null;
  let bestYear = Number.NEGATIVE_INFINITY;
  for (const row of rows) {
    if (row === null || typeof row !== 'object' || Array.isArray(row)) {
      continue;
    }
    const record = row as Record<string, unknown>;
    const year = typeof record.year_roc === 'number' ? record.year_roc : Number.NaN;
    if (Number.isFinite(year) && year > bestYear) {
      bestYear = year;
      best = record;
    }
  }
  return best;
}

/** 新北市行政區代碼是 8 位數字（65000010…65000290）。 */
function isDistrictIdKey(key: string): boolean {
  return /^\d{8}$/.test(key);
}

interface DistrictIndex {
  nameById: Map<string, string>;
  idByName: Map<string, string>;
}

/**
 * 掃過整個 artifact，把所有同時出現 `district_id` 與 `district_name` 的地方
 * 收集成雙向對照表。
 *
 * 刻意從 artifact 自己的內容建立，而不是引用 `data-pipeline/config/districts.json`：
 * 對照表的權威來源應該是這份快照本身。如果快照裡的代碼和 config 不一致，
 * 用 config 去補會產生一個「這份資料裡其實不存在」的行政區名稱。
 */
function buildDistrictIndex(payload: unknown): DistrictIndex {
  const nameById = new Map<string, string>();
  const idByName = new Map<string, string>();

  const visit = (node: unknown): void => {
    if (node === null || typeof node !== 'object') {
      return;
    }
    if (Array.isArray(node)) {
      for (const item of node) {
        visit(item);
      }
      return;
    }
    const record = node as Record<string, unknown>;
    const id = asString(record.district_id);
    const name = asString(record.district_name);
    if (id !== null && name !== null) {
      nameById.set(id, name);
      idByName.set(name, id);
    }
    for (const [key, value] of Object.entries(record)) {
      // villages 有 1032 筆，掃它只是白費時間；它帶的行政區對照
      // 在 districts[] 裡一定也有。
      if (key === 'villages') {
        continue;
      }
      visit(value);
    }
  };

  visit(payload);
  return { nameById, idByName };
}

function asString(value: unknown): string | null {
  return typeof value === 'string' && value.length > 0 ? value : null;
}
