import type { AiContext, AiEvidence } from '../types/aiEvidence.js';
import type { StructuredOutput } from '../types/structuredOutput.js';
import { formatEvidenceForPrompt, formatKnownLimitations } from './guardrails.js';

/**
 * 放進 system prompt 的示範，不是真的資料。
 *
 * 為什麼不只用文字描述規則、還要給完整範例：LLM 模仿具體範例的格式穩定度，
 * 通常比單靠文字規則描述好很多，尤其是「limitations 要寫得具體」這種很難用規則講清楚的要求。
 *
 * ⚠️ 範例的 period 一律用 `00000`。這是刻意的：`00000` 不是合法的民國期間，
 * 所以範例的 evidenceId 永遠不可能跟真實 evidenceId 撞號。如果模型不小心引用了
 * 範例的 ID，`runFeature` 的驗證會抓到，而不是讓一個看起來合理的假引用混過去。
 *
 * 欄位與 metricId 都用**真實的**（`youth_18_35_total`、`position_count`、
 * `youthEligibility` 的三個值），這樣模型學到的是實際會遇到的詞彙。
 */
const exampleEvidence: AiEvidence[] = [
  {
    evidenceId: 'population:00000:0:youth_18_35_total',
    dataset: 'population',
    source: 'moi_household_registration',
    sourceRecordId: 'population:00000000:0000-00',
    geoLevel: 'district',
    districtId: '65000010',
    districtName: '板橋區',
    period: '00000',
    periodStart: '2000-01-01',
    periodEnd: '2000-01-31',
    periodType: 'month',
    metricId: 'youth_18_35_total',
    metricSource: 'metric_id',
    value: 128000,
    unit: 'people',
    ageScope: 'derived_18_35',
    youthEligibility: 'eligible',
    qualityFlags: [],
    sourcePath: 'curated/population.json',
    sourceUrl: null,
    sourceKind: 'dataset',
    computation: null,
    fetchedAt: '2000-01-01T00:00:00+00:00',
  },
  {
    evidenceId: 'population:00000:1:youth_18_35_total',
    dataset: 'population',
    source: 'moi_household_registration',
    sourceRecordId: 'population:00000000:0000-00',
    geoLevel: 'district',
    districtId: '65000020',
    districtName: '三重區',
    period: '00000',
    periodStart: '2000-01-01',
    periodEnd: '2000-01-31',
    periodType: 'month',
    metricId: 'youth_18_35_total',
    metricSource: 'metric_id',
    value: 89000,
    unit: 'people',
    ageScope: 'derived_18_35',
    youthEligibility: 'eligible',
    qualityFlags: [],
    sourcePath: 'curated/population.json',
    sourceUrl: null,
    sourceKind: 'dataset',
    computation: null,
    fetchedAt: '2000-01-01T00:00:00+00:00',
  },
  {
    evidenceId: 'job_vacancies:00000:0:position_count',
    dataset: 'job_vacancies',
    source: 'taiwanjobs',
    sourceRecordId: 'job_vacancies:0000000000000000',
    geoLevel: 'district',
    districtId: '65000010',
    districtName: '板橋區',
    period: '00000',
    periodStart: '2000-01-01',
    periodEnd: '2000-01-01',
    periodType: 'snapshot',
    metricId: 'position_count',
    metricSource: 'record_field',
    value: 5,
    unit: 'positions',
    ageScope: 'not_age_specific',
    youthEligibility: 'context_only',
    qualityFlags: [],
    sourcePath: 'curated/job_vacancies.json',
    // 職缺有逐筆網址（實測在 raw_record 的 URL_QUERY 欄位），範例也示範一下這個欄位。
    sourceUrl: 'https://job.taiwanjobs.gov.tw/Internet/jobwanted/JobDetail.aspx?EXAMPLE',
    sourceKind: 'dataset',
    computation: null,
    fetchedAt: '2000-01-01T00:00:00+00:00',
  },
];

export const FEW_SHOT_EXAMPLE_CONTEXT: AiContext = {
  question: null,
  focusDistrict: null,
  focusArea: 'employment',
  evidence: exampleEvidence,
  knownLimitations: [
    'job_vacancies 僅取樣 200 筆，實際符合條件共 3896 筆；這是為了控制 prompt 長度而截斷，不代表資料只有這麼多，也不可據此推論全體分布。',
  ],
  // 範例不示範網路搜尋：多一個變數會讓模型分心，而且網路搜尋的規則已經
  // 在 formatWebFindings() 的區塊裡講得很清楚了。
  webFindings: [],
};

/**
 * 這份範例輸出示範的重點，依重要性排序：
 * 1. **不自己算**：只有一筆職缺 record_field，就誠實說「無法判斷全區職缺水準」，
 *    而不是拿 position_count=5 去推估或跟人口數相除。
 * 2. **每個 basis 的 note 都寫出資料提供者**：這是本服務最重要的要求。
 * 3. **尊重 youthEligibility**：職缺是 context_only，所以不當青年專屬數據解讀。
 * 4. **既知限制原封不動帶出來**：取樣 200/3896 那句照抄進 limitations。
 */
export const FEW_SHOT_EXAMPLE_OUTPUT: StructuredOutput = {
  // 第 1 步的產物。示範重點：contextOnlyMetrics 與 youthSpecificMetrics 要分清楚，
  // 而 missingForQuestion 非空就直接決定了下一行不可能是 sufficient。
  evidenceReview: {
    availableMetrics: [
      'youth_18_35_total（板橋區／00000）',
      'youth_18_35_total（三重區／00000）',
      'position_count（板橋區／00000 單筆職缺）',
    ],
    youthSpecificMetrics: ['youth_18_35_total（板橋區、三重區，youthEligibility=eligible）'],
    contextOnlyMetrics: ['position_count（youthEligibility=context_only，非青年專屬職缺）'],
    missingForQuestion: [
      '各區職缺總數（目前只有單筆職缺的職位數，無法代表全區）',
      '各區薪資中位數',
      '居住負擔（房價、租金）與交通可及性',
    ],
  },
  // partial：青年人口有分區資料可用，但就業側缺彙總指標。這正是最常見的實際情況，
  // 所以範例刻意示範 partial 而不是 sufficient——示範「部分能答」怎麼寫才誠實。
  dataSufficiency: 'partial',
  issues: [
    '板橋區 18–35 歲青年人口（128,000 人）明顯多於三重區（89,000 人），但目前職缺資料只有單筆職缺的職位數，沒有全區彙總的職缺總量，因此無法判斷板橋區較多的青年人口是否有相應的就業機會承接。',
  ],
  strengths: [
    '板橋區與三重區的青年人口資料都標記為 eligible，代表可證明涵蓋 18–35 歲區間，是可直接引用的青年核心資料，不需要用年齡組推估。',
  ],
  resourceGaps: [
    '青年人口有分區資料，但就業機會這一側只有逐筆職缺記錄、沒有分區彙總指標，兩側的資料粒度不對等，無法計算「每位青年可對應多少職缺」這類供需落差。',
  ],
  policyDirections: [
    '建議先補齊分區的職缺彙總指標（例如各區職缺總數、薪資中位數），才能把青年人口與就業機會放在同一個粒度上比較；在此之前，關於供需落差的判斷都只能是方向性的假設。',
  ],
  basis: [
    {
      evidenceId: 'population:00000:0:youth_18_35_total',
      note: '依據內政部戶政司戶籍人口統計，板橋區 18–35 歲青年人口 128,000 人，youthEligibility=eligible',
    },
    {
      evidenceId: 'population:00000:1:youth_18_35_total',
      note: '依據內政部戶政司戶籍人口統計，三重區 18–35 歲青年人口 89,000 人，低於板橋區',
    },
    {
      evidenceId: 'job_vacancies:00000:0:position_count',
      note: '依據勞動部勞動力發展署（台灣就業通）求才職缺資料，板橋區單一職缺的職位數 5 個；metricSource=record_field，單筆不代表全區職缺總量',
    },
  ],
  webReferences: [],
  limitations: [
    'job_vacancies 僅取樣 200 筆，實際符合條件共 3896 筆；這是為了控制 prompt 長度而截斷，不代表資料只有這麼多，也不可據此推論全體分布。',
    '職缺資料的 youthEligibility 是 context_only，沒有年齡區分，不可解讀成青年專屬職缺。',
    '目前沒有各區職缺總數、薪資中位數等彙總指標，因此無法量化青年人口與就業機會之間的落差。',
    '本次 evidence 未包含居住負擔（房價、租金）與交通可及性資料，無法評估青年在當地的整體生活條件。',
  ],
  disclaimer: 'AI 建議屬於政策輔助資訊，不代表政府正式政策決定。',
};

/**
 * 第二個範例：**資料不足**的情況。
 *
 * 為什麼一定要有這個範例：這是我們最在意的失敗模式。模型天生傾向「總得說點什麼」，
 * 給它一堆人口資料然後問就業問題，它很容易硬答。只用文字規則講「資料不足要說不知道」
 * 效果有限，直接示範一次「四塊全空長什麼樣」有效得多。
 *
 * 情境：使用者問薪資，但 evidence 只有人口資料。
 */
export const FEW_SHOT_INSUFFICIENT_OUTPUT: StructuredOutput = {
  evidenceReview: {
    availableMetrics: ['youth_18_35_total（板橋區／00000）'],
    youthSpecificMetrics: ['youth_18_35_total（youthEligibility=eligible）'],
    contextOnlyMetrics: [],
    // 使用者問薪資，evidence 一筆薪資資料都沒有 —— 這直接決定了 insufficient。
    missingForQuestion: [
      '薪資資料（本次 evidence 完全沒有任何薪資指標）',
      '職缺與就業相關指標',
    ],
  },
  dataSufficiency: 'insufficient',
  // 四塊全空。這是 schema 強制的，也是這個範例要示範的重點。
  issues: [],
  strengths: [],
  resourceGaps: [],
  policyDirections: [],
  basis: [],
  webReferences: [],
  limitations: [
    '本次 evidence 只有板橋區的青年人口數，沒有任何薪資指標，因此無法回答關於薪資水準的問題。',
    '不會用人口數推估薪資，也不會引用其他地區或其他年度的薪資資料代答。',
    '若要回答這個問題，需要各區的薪資中位數或平均薪資指標。',
  ],
  disclaimer: '目前資料不足，未產生分析內容。AI 建議屬於政策輔助資訊，不代表政府正式政策決定。',
};

/**
 * 格式化成可以直接放進 system prompt 的文字區塊。
 *
 * 位置在思考程序與規則之後、真正的 evidence 之前，讓模型先看過
 * 「程序 → 規則 → 兩個範例」再處理真正的請求。
 *
 * 給兩個範例而不是一個：一個示範「部分能答怎麼寫」，一個示範「不能答怎麼寫」。
 * 只給前者的話，模型會以為每次都該產出四塊內容。
 */
export function formatFewShotExample(): string {
  return [
    '範例（示範用，不是真的資料。注意 period=00000 不是合法期間，所以這些 evidenceId 永遠不會出現在真實請求裡，不要引用它們）：',
    '',
    '── 範例 A：部分資料可用（dataSufficiency=partial）──',
    '',
    '輸入 evidence：',
    formatEvidenceForPrompt(FEW_SHOT_EXAMPLE_CONTEXT.evidence),
    '',
    formatKnownLimitations(FEW_SHOT_EXAMPLE_CONTEXT.knownLimitations) ?? '',
    '',
    '好的輸出：',
    JSON.stringify(FEW_SHOT_EXAMPLE_OUTPUT, null, 2),
    '',
    [
      '範例 A 做到了六件事：',
      '(1) 先在 evidenceReview 盤點，才寫結論；沒有先寫結論再回頭湊 basis；',
      '(2) missingForQuestion 非空，所以 dataSufficiency 是 partial 而不是 sufficient；',
      '(3) 只有單筆 record_field 職缺資料時，誠實說「無法判斷全區水準」，沒有拿它去推估或跟人口數相除；',
      '(4) 每一條 basis 的 note 都寫出資料提供者（內政部戶政司、勞動部勞動力發展署）；',
      '(5) 尊重 youthEligibility=context_only，沒有把職缺當成青年專屬數據；',
      '(6) 把「已知的資料限制」原封不動抄進 limitations。',
    ].join('\n'),
    '',
    '── 範例 B：資料不足（dataSufficiency=insufficient）──',
    '',
    '情境：使用者問「板橋區青年薪資水準如何？」，但 evidence 只有人口資料，沒有任何薪資指標。',
    '',
    '好的輸出：',
    JSON.stringify(FEW_SHOT_INSUFFICIENT_OUTPUT, null, 2),
    '',
    [
      '範例 B 的重點：**四塊結論全部留空**。',
      '不要因為「總得說點什麼」而用人口數去推測薪資，也不要引用其他地區或其他年度的資料代答。',
      'limitations 要具體說出缺什麼指標，不是只寫「資料有限」。',
      '誠實說無法回答，比硬答有價值 —— 這是這個服務最重要的行為。',
      '',
      '你的正式回答要做到跟這兩個範例同樣的標準。',
    ].join('\n'),
  ].join('\n');
}
