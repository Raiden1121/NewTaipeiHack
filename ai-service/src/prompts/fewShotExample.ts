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
 * 4. **limitations 只寫新發現的限制**：context 已經給的既知限制（取樣 200/3896 那句）
 *    刻意**不出現**在這裡 —— 那些由 `withKnownLimitations()` 自動附加。
 *    範例如果照抄，模型就會學著照抄，那正是實測佔掉 25% 輸出的行為。
 */
export const FEW_SHOT_EXAMPLE_OUTPUT: StructuredOutput = {
  // 這份範例是給六塊格式（explain / policyCopilot）用的，那兩個功能沒有使用者問題，
  // 所以 answer 是 null。Q&A 的範例在 FEW_SHOT_QA_OUTPUT。
  answer: null,
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
    // 注意：context 的既知限制（job_vacancies 取樣 200/3896）刻意不列在這裡。
    // 模型不需要抄，系統會附加。這裡只有模型自己從 evidence 看出來的新限制。
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
  answer: null,
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
/**
 * 把範例輸出轉成「模型實際該輸出的形狀」再序列化。
 *
 * 這一步不能省。範例物件是完整的 `StructuredOutput`（型別要求四個
 * evidenceReview 子欄位都在），但模型現在**只能**輸出 `missingForQuestion`
 * —— 另外三個由程式盤點，而且 JSON Schema 的 `additionalProperties: false`
 * 會直接拒絕它們。
 *
 * 如果範例照著完整物件印出來，就會出現「範例示範的形狀是 schema 明文禁止的」
 * 這種自相矛盾的 prompt。模型要嘛照範例做然後被 Bedrock 擋掉，要嘛照 schema 做
 * 然後懷疑範例，兩種都不好。
 */
function toModelFacingJson(output: StructuredOutput, includeAnswer: boolean): string {
  const shaped: Record<string, unknown> = {
    // 順序跟 JSON Schema 的 properties 一致，因為那就是要模型走的思考順序。
    evidenceReview: { missingForQuestion: output.evidenceReview.missingForQuestion },
    dataSufficiency: output.dataSufficiency,
  };
  if (includeAnswer) {
    shaped.answer = output.answer;
  }
  shaped.basis = output.basis;
  shaped.issues = output.issues;
  shaped.strengths = output.strengths;
  shaped.resourceGaps = output.resourceGaps;
  shaped.policyDirections = output.policyDirections;
  shaped.webReferences = output.webReferences;
  shaped.limitations = output.limitations;
  shaped.disclaimer = output.disclaimer;
  return JSON.stringify(shaped, null, 2);
}

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
    toModelFacingJson(FEW_SHOT_EXAMPLE_OUTPUT, false),
    '',
    [
      '範例 A 做到了六件事：',
      '(1) 先在 evidenceReview 盤點，才寫結論；沒有先寫結論再回頭湊 basis；',
      '(2) missingForQuestion 非空，所以 dataSufficiency 是 partial 而不是 sufficient；',
      '(3) 只有單筆 record_field 職缺資料時，誠實說「無法判斷全區水準」，沒有拿它去推估或跟人口數相除；',
      '(4) 每一條 basis 的 note 都寫出資料提供者（內政部戶政司、勞動部勞動力發展署）；',
      '(5) 尊重 youthEligibility=context_only，沒有把職缺當成青年專屬數據；',
      '(6) limitations 只寫自己新看出來的限制，**沒有抄寫上面「已知的資料限制」**（系統會自動附加）。',
    ].join('\n'),
    '',
    '── 範例 B：資料不足（dataSufficiency=insufficient）──',
    '',
    '情境：使用者問「板橋區青年薪資水準如何？」，但 evidence 只有人口資料，沒有任何薪資指標。',
    '',
    '好的輸出：',
    toModelFacingJson(FEW_SHOT_INSUFFICIENT_OUTPUT, false),
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

/**
 * Q&A 專屬範例：**純查值問題**。
 *
 * 為什麼 Q&A 需要自己的範例，不能沿用上面那兩個：
 * 上面示範的是六塊格式（`answer` 是 null、四塊有內容）。如果 Q&A 的 prompt 只給
 * 那種範例，模型看到的是「範例都在填四塊、沒有人填 answer」，於是它會照做 ——
 * 而 Q&A 的 schema 要求 answer 必填、四塊在查值問題時應該留空。範例與 schema
 * 打架的時候，範例通常贏。
 *
 * 這個範例示範的重點：
 * 1. **第一句就給被問到的數字**，不先鋪陳背景。
 * 2. **四塊全空**。使用者只是問一個數值，不需要政策分析。
 * 3. `basis` 仍然要有 —— 回答是主張，主張必須可追溯。
 */
export const FEW_SHOT_QA_OUTPUT: StructuredOutput = {
  answer:
    '板橋區 18–35 歲青年人口為 128,000 人。這個數字來自內政部戶政司戶籍人口統計，' +
    '標記為 eligible（可證明涵蓋 18–35 歲區間），可以直接當青年人口引用。' +
    '同一批資料中三重區為 89,000 人，板橋區較多。',
  evidenceReview: {
    availableMetrics: [],
    youthSpecificMetrics: [],
    contextOnlyMetrics: [],
    // 使用者問的就是青年人口，evidence 剛好有 —— 所以這裡是空的，
    // 而空的 missingForQuestion 才允許 dataSufficiency=sufficient。
    missingForQuestion: [],
  },
  dataSufficiency: 'sufficient',
  // 四塊全空：使用者問的是數值，不是政策建議。
  issues: [],
  strengths: [],
  resourceGaps: [],
  policyDirections: [],
  basis: [
    {
      evidenceId: 'population:00000:0:youth_18_35_total',
      note: '依據內政部戶政司戶籍人口統計，板橋區 18–35 歲青年人口 128,000 人，youthEligibility=eligible',
    },
    {
      evidenceId: 'population:00000:1:youth_18_35_total',
      note: '依據內政部戶政司戶籍人口統計，三重區 18–35 歲青年人口 89,000 人，用於與板橋區比較大小',
    },
  ],
  webReferences: [],
  limitations: [],
  disclaimer: 'AI 建議屬於政策輔助資訊，不代表政府正式政策決定。',
};

/**
 * Q&A 專屬範例：**政策類問題**，四塊才派上用場。
 *
 * 有這個範例才不會讓模型以為「Q&A 一律不填四塊」。判斷標準是使用者問的是
 * 「是多少」還是「該怎麼做」。
 */
export const FEW_SHOT_QA_POLICY_OUTPUT: StructuredOutput = {
  answer:
    '就目前的資料只能給方向性的判斷。板橋區青年人口 128,000 人、三重區 89,000 人，' +
    '但職缺這一側只有單筆記錄（某一個職缺的職位數 5 個），沒有各區的職缺總量，' +
    '所以無法比較兩區的「青年人數對就業機會」是否失衡。' +
    '在補齊分區職缺彙總指標之前，任何關於供需落差的建議都只能是假設。',
  evidenceReview: {
    availableMetrics: [],
    youthSpecificMetrics: [],
    contextOnlyMetrics: [],
    missingForQuestion: ['各區職缺總數（目前只有單筆職缺的職位數，無法代表全區）', '各區薪資中位數'],
  },
  dataSufficiency: 'partial',
  issues: [
    '板橋區青年人口（128,000 人）明顯多於三重區（89,000 人），但缺少各區職缺總量，無法判斷較多的青年人口是否有相應的就業機會承接。',
  ],
  strengths: [
    '兩區的青年人口都是 youthEligibility=eligible，可直接引用，不需要用年齡組推估。',
  ],
  resourceGaps: [
    '青年人口有分區資料，就業機會只有逐筆記錄，兩側粒度不對等，無法計算供需落差。',
  ],
  policyDirections: [
    '建議先補齊分區職缺彙總指標（職缺總數、薪資中位數），才能把青年人口與就業機會放在同一個粒度上比較。',
  ],
  basis: [
    {
      evidenceId: 'population:00000:0:youth_18_35_total',
      note: '依據內政部戶政司戶籍人口統計，板橋區 18–35 歲青年人口 128,000 人',
    },
    {
      evidenceId: 'job_vacancies:00000:0:position_count',
      note: '依據勞動部勞動力發展署（台灣就業通）求才職缺資料，板橋區單一職缺的職位數 5 個；metricSource=record_field，單筆不代表全區',
    },
  ],
  webReferences: [],
  limitations: [
    '職缺資料的 youthEligibility 是 context_only，沒有年齡區分，不可解讀成青年專屬職缺。',
  ],
  disclaimer: 'AI 建議屬於政策輔助資訊，不代表政府正式政策決定。',
};

/**
 * Q&A 的 few-shot 區塊。
 *
 * 兩個範例的分工就是 Q&A 最容易做錯的兩件事：查值問題硬塞四塊分析，
 * 以及政策問題只回一句話卻不給分析。
 */
export function formatQaFewShotExample(): string {
  return [
    '範例（示範用，不是真的資料。注意 period=00000 不是合法期間，所以這些 evidenceId 永遠不會出現在真實請求裡，不要引用它們）：',
    '',
    '輸入 evidence（兩個範例共用）：',
    formatEvidenceForPrompt(FEW_SHOT_EXAMPLE_CONTEXT.evidence),
    '',
    '── 範例 A：使用者問「板橋區的青年人口是多少？」（純查值）──',
    '',
    '好的輸出：',
    toModelFacingJson(FEW_SHOT_QA_OUTPUT, true),
    '',
    [
      '範例 A 的重點：',
      '(1) **answer 第一句就給被問到的數字**，沒有先鋪陳背景或分析；',
      '(2) **四塊全部留空** —— 使用者問的是數值，硬塞政策分析只是把同一件事換句話再講一次；',
      '(3) 即使如此，basis 仍然有兩筆：回答是一個主張，主張必須可追溯；',
      '(4) missingForQuestion 是空的，所以 dataSufficiency 可以是 sufficient。',
    ].join('\n'),
    '',
    '── 範例 B：使用者問「板橋區的青年就業機會夠嗎？可以怎麼改善？」（政策類）──',
    '',
    '好的輸出：',
    toModelFacingJson(FEW_SHOT_QA_POLICY_OUTPUT, true),
    '',
    [
      '範例 B 的重點：',
      '(1) answer 仍然是直接回答（「只能給方向性的判斷」＋原因），不是把四塊摘要一遍；',
      '(2) 因為問的是政策，四塊這次**有**內容；',
      '(3) 缺少關鍵資料時誠實說「無法比較」，沒有拿單筆職缺去推估全區。',
    ].join('\n'),
    '',
    '── 範例 C：使用者問「為何示範三區薪資第二高？」（為什麼，而且前提是錯的）──',
    '',
    '輸入 evidence（這個範例另外一組）：',
    formatWhyExampleEvidence(),
    '',
    '好的輸出：',
    toModelFacingJson(FEW_SHOT_WHY_OUTPUT, true),
    '',
    [
      '範例 C 的重點，這是「為什麼」類問題最容易做錯的三件事：',
      '(1) **更正前提。** 使用者說第二高，資料顯示第三高 —— answer 第一句就更正，',
      '    並講出前兩名各是多少。照抄錯誤前提然後在錯的基礎上解釋，比答不出來更糟。',
      '(2) **相關不是因果。** 用「方向一致」「可能與…有關」，並在最後明確說',
      '    「資料本身無法判斷原因，上面說的只是同時出現的現象」。',
      '(3) **樣本數警告。** 職缺薪資中位數的母體是求才職缺，職缺少的區容易被少數高薪職缺拉高。',
      '    偏遠行政區排名異常高的時候，這一點一定要講。',
      '(4) 四塊**全空** —— 「為什麼」是解釋題，不是政策題。',
      '',
      '判斷標準：問「是多少」「為什麼」「排第幾」都只給 answer；只有問「該怎麼做」才填四塊。',
      '你的正式回答要做到跟這三個範例同樣的標準。',
    ].join('\n'),
  ].join('\n');
}

/**
 * Q&A 專屬範例三：**「為什麼」問題，而且使用者的前提是錯的。**
 *
 * 這是 Q&A 最重要也最容易做錯的一題，所以值得多花 prompt 空間示範。
 *
 * 三個示範重點，每一個都對應一個實際會犯的錯：
 *
 * 1. **更正前提。** 使用者說「第二高」，資料顯示是第三高。照抄前提然後在錯的基礎上
 *    解釋，比答不出來更糟 —— 使用者會帶著一個被 AI 確認過的錯誤認知離開。
 * 2. **相關不是因果。** 用「方向一致」「可能與…有關」，不寫「因為 A 所以 B」。
 * 3. **樣本數警告。** 偏遠行政區的職缺很少，少數幾筆高薪職缺就會把中位數拉高。
 *    這是這份資料真實存在的陷阱（實測坪林、烏來這種區排在最前面），
 *    看到偏遠區排名異常高就必須講。
 *
 * 用的是**假的**行政區資料（period=00000），所以不會被誤引用。
 */
const FEW_SHOT_WHY_EVIDENCE: AiEvidence[] = [
  {
    evidenceId: 'analytics_dashboard_overview:00000:示範一區:salary_median',
    dataset: 'analytics_dashboard_overview',
    source: 'newtaipei_youth_analytics',
    sourceRecordId: null,
    sourceUrl: null,
    sourceKind: 'dataset',
    geoLevel: 'district',
    districtId: '65099910',
    districtName: '示範一區',
    period: '00000',
    periodStart: null,
    periodEnd: null,
    periodType: 'snapshot',
    metricId: 'salary_median',
    metricSource: 'analytics_metric',
    value: 38000,
    unit: 'TWD/月',
    computation: 'analytics:dashboard_overview.districts.salary_median @00000',
    ageScope: 'not_age_specific',
    youthEligibility: 'context_only',
    qualityFlags: [],
    sourcePath: 'analytics/published/00000/dashboard_overview.json',
    fetchedAt: '2000-01-01T00:00:00+00:00',
  },
  {
    evidenceId: 'analytics_dashboard_overview:00000:示範二區:salary_median',
    dataset: 'analytics_dashboard_overview',
    source: 'newtaipei_youth_analytics',
    sourceRecordId: null,
    sourceUrl: null,
    sourceKind: 'dataset',
    geoLevel: 'district',
    districtId: '65099920',
    districtName: '示範二區',
    period: '00000',
    periodStart: null,
    periodEnd: null,
    periodType: 'snapshot',
    metricId: 'salary_median',
    metricSource: 'analytics_metric',
    value: 37000,
    unit: 'TWD/月',
    computation: 'analytics:dashboard_overview.districts.salary_median @00000',
    ageScope: 'not_age_specific',
    youthEligibility: 'context_only',
    qualityFlags: [],
    sourcePath: 'analytics/published/00000/dashboard_overview.json',
    fetchedAt: '2000-01-01T00:00:00+00:00',
  },
  {
    evidenceId: 'analytics_dashboard_overview:00000:示範三區:salary_median',
    dataset: 'analytics_dashboard_overview',
    source: 'newtaipei_youth_analytics',
    sourceRecordId: null,
    sourceUrl: null,
    sourceKind: 'dataset',
    geoLevel: 'district',
    districtId: '65099930',
    districtName: '示範三區',
    period: '00000',
    periodStart: null,
    periodEnd: null,
    periodType: 'snapshot',
    metricId: 'salary_median',
    metricSource: 'analytics_metric',
    value: 36500,
    unit: 'TWD/月',
    computation: 'analytics:dashboard_overview.districts.salary_median @00000',
    ageScope: 'not_age_specific',
    youthEligibility: 'context_only',
    qualityFlags: [],
    sourcePath: 'analytics/published/00000/dashboard_overview.json',
    fetchedAt: '2000-01-01T00:00:00+00:00',
  },
  {
    evidenceId: 'analytics_dashboard_overview:00000:示範三區:high_salary_ratio',
    dataset: 'analytics_dashboard_overview',
    source: 'newtaipei_youth_analytics',
    sourceRecordId: null,
    sourceUrl: null,
    sourceKind: 'dataset',
    geoLevel: 'district',
    districtId: '65099930',
    districtName: '示範三區',
    period: '00000',
    periodStart: null,
    periodEnd: null,
    periodType: 'snapshot',
    metricId: 'high_salary_ratio',
    metricSource: 'analytics_metric',
    value: 0.046,
    unit: '比例(0-1)',
    computation: 'analytics:dashboard_overview.districts.high_salary_ratio @00000',
    ageScope: 'not_age_specific',
    youthEligibility: 'context_only',
    qualityFlags: [],
    sourcePath: 'analytics/published/00000/dashboard_overview.json',
    fetchedAt: '2000-01-01T00:00:00+00:00',
  },
];

export const FEW_SHOT_WHY_OUTPUT: StructuredOutput = {
  answer:
    '示範三區的職缺薪資中位數是 36,500 元/月，在這批資料裡排第 3 高，不是第 2 高' +
    '（第 1 是示範一區 38,000 元，第 2 是示範二區 37,000 元）。' +
    '就同一份資料能看到的部分，示範三區的高薪職缺比例為 4.60%，' +
    '這個指標與薪資中位數的方向一致，可能與該區職缺結構有關。' +
    '不過要提醒兩件事：這兩個指標的 youthEligibility 都是 context_only，' +
    '是全體職缺的統計而非青年專屬；而且薪資中位數來自求才職缺，' +
    '如果該區的職缺筆數不多，少數幾筆高薪職缺就足以把中位數拉高。' +
    '資料本身無法判斷薪資排名的原因，上面說的只是同時出現的現象，不是因果關係。',
  evidenceReview: {
    availableMetrics: [],
    youthSpecificMetrics: [],
    contextOnlyMetrics: [],
    missingForQuestion: [
      '各區的職缺筆數（無法判斷薪資中位數的樣本是否足夠代表該區）',
      '各區的產業結構或職類分布（無法解釋職缺結構為何不同）',
    ],
  },
  dataSufficiency: 'partial',
  // 「為什麼」是解釋題，不是政策題 —— 四塊全空。
  issues: [],
  strengths: [],
  resourceGaps: [],
  policyDirections: [],
  basis: [
    {
      evidenceId: 'analytics_dashboard_overview:00000:示範三區:salary_median',
      note: '依據本專案資料管線彙總指標，示範三區職缺薪資中位數 36,500 元/月，youthEligibility=context_only',
    },
    {
      evidenceId: 'analytics_dashboard_overview:00000:示範一區:salary_median',
      note: '依據本專案資料管線彙總指標，示範一區 38,000 元/月，為這批資料的最高值，用於更正排名',
    },
    {
      evidenceId: 'analytics_dashboard_overview:00000:示範二區:salary_median',
      note: '依據本專案資料管線彙總指標，示範二區 37,000 元/月，排第 2，用於更正排名',
    },
    {
      evidenceId: 'analytics_dashboard_overview:00000:示範三區:high_salary_ratio',
      note: '依據本專案資料管線彙總指標，示範三區高薪職缺比例 4.60%，與薪資中位數方向一致',
    },
  ],
  webReferences: [],
  limitations: [
    '薪資中位數與高薪職缺比例的 youthEligibility 均為 context_only，是全體職缺統計，不是青年專屬薪資。',
    '職缺薪資中位數的母體是求才職缺，職缺數少的行政區容易被少數高薪職缺拉高，排名不宜過度解讀。',
    '本次資料無法判斷排名成因，answer 中提到的關聯僅為同時出現的現象，非因果關係。',
  ],
  disclaimer: 'AI 建議屬於政策輔助資訊，不代表政府正式政策決定。',
};

/** 「為什麼」範例的 evidence 區塊，給 `formatQaFewShotExample()` 用。 */
export function formatWhyExampleEvidence(): string {
  return formatEvidenceForPrompt(FEW_SHOT_WHY_EVIDENCE);
}
