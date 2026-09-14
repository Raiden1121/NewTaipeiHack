/**
 * 從使用者的問題推導「需要拿全 29 區來比較的指標」。
 *
 * ## 為什麼需要這個
 *
 * `buildAiContext` 看到 `focusDistrict` 就會把 evidence 篩成那一區，否則 29 區
 * 全撈進來會爆掉。但那個預設會讓一整類問題**根本答不出來**：
 *
 * > 「為何八里薪資第六高？」
 *
 * 要回答這題（甚至只是要確認「第六高」對不對）就必須有全 29 區的 `salary_median`。
 * 只給八里一區的話，模型看得到 35,835 這個數字，卻完全無法知道它排第幾 ——
 * 於是只能照抄使用者的前提，而使用者的前提**可能是錯的**
 * （實測八里其實是第五高，不是第六）。照抄錯誤前提比答不出來更糟。
 *
 * ## 為什麼用關鍵字，不用模型判斷
 *
 * 「這個問題在問哪個指標」讓模型判斷會準一些，但那是**多一輪 LLM 往返**，
 * 而延遲是這個服務最大的風險。關鍵字對應是確定性的、零延遲、可測試，
 * 而且判斷錯的代價很小：多給幾個指標只是多幾十筆 evidence，
 * 少給則退回原本的單區行為（模型會誠實說缺跨區資料）。
 *
 * ## 判斷失誤的方向是刻意的
 *
 * 寧可多比對到（多撈 29 筆 × 幾個指標）也不要漏 —— 漏掉的後果是模型無法驗證
 * 使用者的前提，而多撈的後果只是 prompt 長一點。
 */

/**
 * ## 覆蓋率是量出來的，不是憑感覺列的
 *
 * 這張表用 `dashboard_overview` 與各 `analyses/*.json` 的 `districts[]` 稽核過：
 * 把「29 區幾乎都有值」（也就是能拿來排名）的指標全部列出來，逐一對照表裡有沒有。
 *
 * 第一次稽核的結果是 **17 個指標只在 `focusMetricIds`、46 個兩個表都沒有**，
 * 而那正好對應到實測踩到的兩個錯誤回答：
 *
 * - 「為什麼八里區的青年薪資分數這麼高？」→ 模型答「無法確認排名」。
 *   實際上 `yoiComponents.salary` 29 區都有值，八里 68.12 分是**第 2 高**。
 *   原因是那個指標只在 `focusMetricIds`，所以只拿到八里自己的分數。
 * - 「怎麼可能新莊的宜居度比板橋還低？」→ 模型答「無法比較」。
 *   實際上 `opportunityIndex` 29 區都有值（板橋 100 第 1、新莊 91.75 第 3），
 *   而且連 `yoiComponents.housing` 也是（板橋 13.88 > 新莊 13.32）。
 *   原因是「宜居度」這個詞不在任何規則的 keywords 裡。
 *
 * 兩次都不是模型的問題 —— 它誠實說了「本次 evidence 沒有」，而那是真的。
 * 是這張表把資料漏掉了。
 *
 * ## 補的原則
 *
 * 1. **面向分數（`yoiComponents.*`）要放進 `metricIds` 而不是只放 focus。**
 *    使用者問「X 分數為什麼這麼高」時，問的就是那個分數的排名。
 * 2. **管線欄位不補**：`status`、`quality_status`、`availableMonths`、
 *    `coverageRatio`、`source_period`、`denominator_type`、`election_year_roc`
 *    這些是資料完整度與維度描述，不是可排名的量測值。
 * 3. **重複命名不補**：`score_salary` 等於 `yoiComponents.salary`、
 *    `salaryMedian` 等於 `salary_median`（快照兩種寫法都有，dedupe 會留一份）。
 *    兩個都放只會讓同一個數字出現兩個 evidenceId。
 */
interface ComparisonRule {
  /** 出現任一個關鍵字就命中 */
  keywords: readonly string[];
  /**
   * 命中後要**跨 29 區**取得的 metricId。
   *
   * 刻意只放「真的需要排名」的那一兩個 —— 每加一個就是 ×29 筆 evidence，
   * 而 input token 直接影響延遲（實測同一個問題 6 筆 vs 250 筆差 7.8 秒）。
   * 同主題的其他指標放 `focusMetricIds`，只對焦點行政區取。
   */
  metricIds: readonly string[];
  /**
   * 同主題但**只對焦點行政區**取的指標，用來解釋數字。
   *
   * 這裡可以放 curated 的欄位名（`salary_lower`、`position_count`…）——
   * 那些是彙總指標的母體，模型看得到它們才能判斷「中位數是不是被少數幾筆拉高的」。
   * 實測坪林那題就是靠逐筆職缺上的 `query_district_mismatch_filtered` 旗標
   * 發現資料有問題的。
   */
  focusMetricIds: readonly string[];
}

/**
 * 關鍵字 → 指標。
 *
 * metricId 用的是 analytics `dashboard_overview` 的欄位名（見
 * `ANALYTICS_METRIC_META`），因為那份 artifact 是唯一 29 區都有、而且欄位口徑
 * 一致的來源 —— 跨區比較必須拿同一個口徑的數字，不然比出來的東西沒有意義。
 *
 * 每條規則刻意多帶幾個相關指標：回答「為何 X 高」需要的不只是 X 本身，
 * 還需要同一個面向的其他指標才有東西可以解釋。例如薪資高不高，
 * `high_salary_ratio`（高薪職缺比例）往往比 `salary_median` 更能說明原因。
 */
export const COMPARISON_METRIC_RULES: readonly ComparisonRule[] = [
  {
    keywords: ['薪資', '薪水', '待遇', '起薪', '所得', '收入', '月薪', '年薪'],
    // `yoiComponents.salary` 從 focus 移上來：實測「為什麼八里的青年薪資分數這麼高」
    // 拿不到其他區的分數，模型只能答「無法確認排名」，而它其實排第 2。
    // `adjusted_youth_wage` 也要跨區：使用者說「青年薪資」時，
    // 誠實的指標是這個（youthEligibility=eligible），而不是 `salary_median`
    // （那是全體職缺統計，context_only）。只有它跨區可比，模型才能回答
    // 「這一區的青年實質薪資排第幾」而不是拿全年齡的數字代答。
    metricIds: [
      'salary_median',
      'high_salary_ratio',
      'yoiComponents.salary',
      'adjusted_youth_wage',
    ],
    focusMetricIds: [
      'adjusted_youth_wage',
      'knowledge_job_ratio',
      'estimated_wage',
      'estimated_monthly_wage',
      'occupation_shannon_index',
      'vacancies_per_10k_youth',
      // 樣本數與收縮後的中位數：判斷「是不是被少數幾筆高薪職缺拉高」的關鍵。
      // 實測坪林那題（中位數全市最高但高薪職缺比例 0）就是靠這類指標看出來的。
      'salary_sample_size',
      'salary_median_shrunk',
      // curated：彙總中位數的母體
      'salary_lower',
      'salary_upper',
      'salary_midpoint',
      'position_count',
    ],
  },
  // 住宅三條規則的 metricIds 都帶上 `yoiComponents.housing`：問房價／租金的人
  // 通常是在追問「為什麼這區的居住分數這麼低」，而那需要跨區才能回答。
  // 實測「新莊宜居度比板橋低」那題就是因為拿不到板橋的 housing 分數而答不出來。
  {
    keywords: ['租金', '房租', '租屋', '租房'],
    metricIds: ['rent_median', 'rent_wage_ratio', 'yoiComponents.housing'],
    focusMetricIds: ['salary_median', 'rent_per_ping', 'rent_total'],
  },
  {
    keywords: ['房價', '買房', '購屋', '房地產'],
    // 薪資中位數是房價是否形成居住負擔的必要比較脈絡。
    // 放在跨區 metricIds 而不是只放 focusMetricIds，才能保證沒有單一
    // focusDistrict 時，新莊／板橋這類被問題點名的行政區仍有可引用的值。
    metricIds: [
      'house_price_median',
      'rent_wage_ratio',
      'yoiComponents.housing',
      'salary_median',
    ],
    focusMetricIds: [
      'house_price_median_wan',
      'salary_median',
      'price_per_ping',
      'total_price',
    ],
  },
  {
    keywords: ['居住', '住房', '房子', '居住負擔', '住得', '房租負擔'],
    metricIds: [
      'rent_median',
      'house_price_median',
      'rent_wage_ratio',
      'yoiComponents.housing',
    ],
    focusMetricIds: ['salary_median', 'adjusted_youth_wage', 'housingScore'],
  },
  {
    keywords: ['職缺', '工作機會', '就業機會', '找工作', '就業'],
    metricIds: ['vacancies_per_10k_youth', 'yoiComponents.job'],
    focusMetricIds: [
      'occupation_shannon_index',
      'high_salary_ratio',
      'salary_median',
      'knowledge_job_ratio',
      'talent_demand_yoy',
      // 每平方公里職缺數：跟每萬青年職缺數是兩種密度口徑，
      // 偏遠區「人少所以人均高」時這個指標會揭穿差異。
      'vacancies_per_km2',
      'position_count',
      'salary_midpoint',
    ],
  },
  {
    keywords: ['人才', '人才需求', '產業'],
    metricIds: ['talent_demand_yoy', 'yoiComponents.talent'],
    focusMetricIds: [
      'college_student_density',
      'knowledge_job_ratio',
      'new_demand_count',
      'new_hired_count',
      'valid_hired_count',
    ],
  },
  {
    keywords: ['職訓', '訓練', '課程', '技能'],
    metricIds: ['training_people_per_10k_youth', 'vt_course_count'],
    focusMetricIds: ['training_people', 'training_hours', 'fee_per_person'],
  },
  {
    keywords: ['交通', '通勤', '捷運', '公車', '軌道', '可及', 'ubike', '腳踏車', '自行車'],
    metricIds: ['yoiComponents.transport', 'railway_stop_density'],
    focusMetricIds: ['bus_stops_per_10k_youth', 'bike_stop_density'],
  },
  {
    keywords: ['生育', '出生', '生小孩', '育兒', '生育率', '少子'],
    metricIds: ['fertilityRate', 'fertilityVsCityAvg', 'fertilityLevel'],
    focusMetricIds: [
      'totalBirths',
      'averageMonthlyFemale18_35',
      'daycareCoverage',
      'fafiScore',
      'fafiLevel',
      'youthRatio',
    ],
  },
  {
    keywords: [
      '人口',
      '青年人數',
      '幾個青年',
      '多少青年',
      '青年有幾人',
      '青年人口數',
      '青年數',
      '青年占比',
      '青年比例',
      '年輕',
    ],
    // youth_ratio（青年占總人口比）與 youth_yoy（青年人口年增率）都是 29 區都有值
    // 而且很常被問排名的指標（「哪一區最年輕」「哪一區青年流失最快」）。
    metricIds: ['youth_18_35_total', 'youth_ratio', 'youth_yoy'],
    focusMetricIds: [
      'people_total',
      'youth_share_percent',
      'annual.population.youth_18_35_total',
      'move_in',
      'move_out',
      'net_migration',
    ],
  },
  {
    // 「宜居」「適合」「整體」「綜合」「名次」都是實測漏掉的問法。
    // 「怎麼可能新莊的宜居度比板橋還低」完全沒有命中任何規則的 keywords
    // （只因為句子裡有「房價」才誤打誤撞拿到房價指標），於是模型答「無法比較」，
    // 而 opportunityIndex 其實 29 區都有值。
    // ⚠️ 刻意**不**收「適合」「整體」這類太泛的詞。
    // 一度加過，結果「哪一區最適合青年？」被判成「機會指數主題」，
    // 於是 inferFocusMetrics 把焦點範圍收斂到機會指數那幾個指標 ——
    // 但那種開放式問題可能牽涉任何面向，收斂反而讓模型缺資料。
    // 開放式問題應該走 HEADLINE_METRIC_IDS（跨區給頭條指標）＋ 焦點不收斂。
    keywords: ['機會指數', '機會', '發展', '宜居', '宜居度', '綜合', '名次', '排進', '總分'],
    metricIds: ['opportunityIndex', 'retentionRiskLevel'],
    // 五個子分數只對焦點行政區取。
    // 刻意不放進 metricIds：5 個 × 29 區 = 145 筆 evidence，而回答「為何這區的
    // 總指數高」需要的是「這一區的哪個子分數突出」，不是每個子分數的全市排名。
    // 實測樹林那題（子分數只有自己這區）就答得很完整：就業 75.80 最高、
    // 交通 15.07 最低，直接指出主因與弱項。
    focusMetricIds: [
      'yoiComponents.job',
      'yoiComponents.salary',
      'yoiComponents.talent',
      'yoiComponents.housing',
      'yoiComponents.transport',
      'yoiRaw',
    ],
  },
  {
    keywords: ['留才', '留下', '流失', '外移', '人口外流', '風險'],
    metricIds: ['retentionRiskLevel', 'opportunityIndex'],
    focusMetricIds: [
      'youth_18_35_total',
      'annual.population.youth_18_35_total',
      'annual.population.youth_share_percent',
      'net_migration',
      'move_in',
      'move_out',
      'yoiComponents.housing',
      'yoiComponents.salary',
    ],
  },
  {
    keywords: ['服務', '據點', '涵蓋', '服務點', '青年中心'],
    metricIds: ['serviceCoverageRate'],
    focusMetricIds: [
      'serviceCoverageStatus',
      'service_coverage.value',
      'service_coverage.covered_youth',
      'service_coverage.youth_population',
      'service_coverage.target_population',
      'service_coverage.village_count',
      'service_coverage.covered_village_count',
      'capacity',
    ],
  },
  {
    keywords: ['參與', '參選', '青年參與', '參政', '選舉', '當選', '候選', '里長', '議員'],
    // 青年參政的比率型指標 29 區都有值，是「哪一區青年參政最踴躍」的答案來源。
    metricIds: [
      'youthParticipationIndex',
      'youthCandidacyRatePer100k',
      'youth_candidacy_rate',
      'youth_borough_chief_ratio',
      'yrr',
    ],
    focusMetricIds: [
      'elections.youth_candidacy.borough_chief_v1.youth_candidacy_rate',
      'elections.youth_candidacy.borough_chief_v1.youth_candidate_count',
      'elections.youth_candidacy.borough_chief_v1.candidate_count',
      'elections.youth_candidacy.borough_chief_v1.age_known_candidate_count',
      'elections.youth_candidacy.borough_chief_v1.youth_elected_count',
      'elections.youth_candidacy.borough_chief_v1.elected_count',
      'elections.youth_candidacy.borough_chief_v1.youth_population_18_35',
      'elections.v1_borough_chief.elected_seat_count',
      'elections.v1_borough_chief.youth_population_share',
      'elections.v1_borough_chief.population_total',
    ],
  },
  {
    // 托育與家庭友善是獨立主題：`育兒` 同時也在生育那條，兩條都命中沒有壞處
    // （多給幾個指標而已），但漏掉的話「為什麼這區的托育覆蓋率低」就答不出來。
    keywords: ['托育', '保母', '托嬰', '幼兒', '家庭友善', '友善', '育兒'],
    metricIds: ['daycareCoverage', 'daycareCoverageScore', 'fafiScore', 'fafiLevel'],
    focusMetricIds: [
      'housingScore',
      'wageScore',
      'daycareCoverageStatus',
      'fertilityRate',
      'averageMonthlyFemale18_35',
      // 涵蓋率的分子與分母：覆蓋率低是「據點少」還是「母體大」要靠這些分辨
      'daycareCoverage.covered_population',
      'daycareCoverage.target_population',
      'daycareCoverage.village_count',
      'daycareCoverage.covered_village_count',
    ],
  },
];

/**
 * 不管問什麼都保留的核心指標。
 *
 * 存在理由是**風險控制**：`inferFocusMetrics()` 用關鍵字判斷主題，判斷錯的時候
 * 模型會拿不到它需要的東西。這幾個是任何問題的共同背景（這區有多少青年、
 * 整體機會指數、留才風險），少了它們連「這個數字在這一區算大還算小」都無從判斷。
 *
 * 刻意保持很短：每一個都會乘上行政區數，而收斂 evidence 的目的就是降低 token。
 */
export const CORE_CONTEXT_METRIC_IDS: readonly string[] = [
  'youth_18_35_total',
  'opportunityIndex',
  'retentionRiskLevel',
  'people_total',
];

/**
 * 帶有「比較意圖」的詞。
 *
 * 命中這些詞、但沒有命中任何指標時，會退回一組頭條指標 ——
 * 「哪一區最好」這種問題沒有指名指標，但顯然需要跨區資料。
 */
const COMPARISON_INTENT_KEYWORDS: readonly string[] = [
  '最高',
  '最低',
  '最多',
  '最少',
  '最好',
  '最差',
  '第幾',
  '排名',
  '排第',
  '排進',
  '名次',
  '比較',
  '相比',
  '比起',
  '比其他',
  '哪一區',
  '哪個區',
  '哪些區',
  '前幾',
  '前段',
  '後段',
  '倒數',
  '墊底',
  '高於',
  '低於',
  '平均',
  // 「分數」「指數」「評分」本身就隱含「跟別人比」——
  // 一個 0–100 的分數單獨看沒有意義，使用者問「這個分數為什麼這麼高」時，
  // 「這麼高」是相對於其他行政區說的。實測漏掉這幾個詞會讓模型答「無法確認排名」。
  '分數',
  '指數',
  '評分',
  '得分',
  '幾分',
];

/** 只講「哪一區最好」時給的頭條指標。 */
const HEADLINE_METRIC_IDS: readonly string[] = [
  'opportunityIndex',
  'retentionRiskLevel',
  'youth_18_35_total',
  'salary_median',
];

export function hasComparisonIntent(question: string): boolean {
  return COMPARISON_INTENT_KEYWORDS.some((keyword) => question.includes(keyword));
}

/**
 * 回傳這個問題需要跨區比較的 metricId（已去重）。
 *
 * 沒有命中任何規則、也沒有比較意圖時回空陣列 —— 那種情況維持原本的單區行為，
 * 不需要多花 prompt 空間。
 */
export function inferComparisonMetrics(question: string | null | undefined): string[] {
  if (typeof question !== 'string' || question.trim().length === 0) {
    return [];
  }

  const matched = new Set<string>();
  for (const rule of COMPARISON_METRIC_RULES) {
    if (rule.keywords.some((keyword) => question.includes(keyword))) {
      for (const metricId of rule.metricIds) {
        matched.add(metricId);
      }
    }
  }

  // 有比較意圖卻對不到具體指標（「哪一區最適合青年？」）時給頭條指標，
  // 否則模型會拿著單一行政區的資料去回答一個比較問題。
  if (matched.size === 0 && hasComparisonIntent(question)) {
    for (const metricId of HEADLINE_METRIC_IDS) {
      matched.add(metricId);
    }
  }

  return [...matched];
}

/**
 * 回傳「焦點行政區這次只需要哪些指標」。**回空陣列代表不要限制。**
 *
 * ## 為什麼要收斂
 *
 * 實測同一個問題在 6 筆 evidence 是 14.1 秒、250 筆是 21.9 秒 —— input 是真的有成本
 * （約 +7.8 秒）。而「為何八里薪資高」這個問題根本不需要生育率、服務涵蓋率、
 * 青年議題關鍵詞那些指標：焦點行政區的 analytics 有 121 筆，其中絕大多數跟問題無關。
 *
 * ## 為什麼安全
 *
 * 三層保護：
 * 1. 關鍵字對不上主題時回空陣列 → 完全維持原本「什麼都給」的行為
 * 2. `CORE_CONTEXT_METRIC_IDS` 永遠包含 → 就算主題判斷錯，基本背景還在
 * 3. 收斂的內容會寫進 `limitations` → 使用者與除錯的人看得到範圍被限縮過
 *
 * 最壞情況是模型少看到一些跟問題無關的指標，而它本來就會誠實說「這部分沒有資料」。
 */
export function inferFocusMetrics(question: string | null | undefined): string[] {
  if (typeof question !== 'string' || question.trim().length === 0) {
    return [];
  }

  const matched = new Set<string>();
  let hitTopic = false;
  for (const rule of COMPARISON_METRIC_RULES) {
    if (rule.keywords.some((keyword) => question.includes(keyword))) {
      hitTopic = true;
      for (const metricId of [...rule.metricIds, ...rule.focusMetricIds]) {
        matched.add(metricId);
      }
    }
  }

  // 主題對不上就不要限制 —— 寧可慢一點，也不要讓模型缺它需要的資料。
  if (!hitTopic) {
    return [];
  }

  for (const metricId of CORE_CONTEXT_METRIC_IDS) {
    matched.add(metricId);
  }
  return [...matched];
}
