/**
 * 驗證思考程序真的有效：`npm run dev:reasoning-check`
 *
 * 這支腳本刻意問**資料回答不了的問題** —— 只餵人口資料，卻問薪資。
 *
 * 這是這個服務最重要也最容易失敗的行為：LLM 天生傾向「總得說點什麼」，
 * 拿到一堆人口數字被問薪資，很容易用人口去「推測」或改答相近的東西。
 * 光看單元測試看不出模型實際會不會這樣做，所以需要真的打一次。
 *
 * 預期結果：
 *   dataSufficiency = insufficient
 *   四塊結論全空、basis 全空
 *   evidenceReview.missingForQuestion 指出缺薪資資料
 *
 * 如果拿到 partial 或 sufficient，就代表 prompt 還不夠強，要回去補。
 */
import { createBedrockClientFromEnv, MockBedrockClient } from '../bedrock/client.js';
import { explainData } from '../handlers/explainData.js';
import { dataQa } from '../handlers/dataQa.js';
import type { AiRequestContext } from '../types/aiEvidence.js';
import type { StructuredOutput } from '../types/structuredOutput.js';

const populationOnly: AiRequestContext['evidence'] = [
  {
    evidenceId: 'population:11507:1:youth_18_35_total',
    dataset: 'population',
    source: 'moi_household_registration',
    sourceRecordId: 'population:65000010:2026-07',
    sourceUrl: null,
    sourceKind: 'dataset',
    geoLevel: 'district',
    districtId: '65000010',
    districtName: '板橋區',
    period: '11507',
    periodStart: '2026-07-01',
    periodEnd: '2026-07-31',
    periodType: 'month',
    metricId: 'youth_18_35_total',
    metricSource: 'metric_id',
    value: 106473,
    unit: 'people',
    ageScope: 'derived_18_35',
    youthEligibility: 'eligible',
    qualityFlags: [],
    sourcePath: 'curated/population.json',
    computation: null,
    fetchedAt: '2026-09-12T01:56:04.525401+00:00',
  },
  {
    // 刻意放一筆機關層級的預算，單位是 TWD_thousand ——
    // 同時測試單位規則（之前模型把 220,101 千元寫成「2 億 2,010 萬千元」）。
    evidenceId: 'youth_budgets:11507:0:budget_amount',
    dataset: 'youth_budgets',
    source: 'ntpc_youth_bureau_budget',
    sourceRecordId: 'youth_budgets:116:proposed_budget',
    sourceUrl: 'https://www.youth.ntpc.gov.tw/example.pdf',
    sourceKind: 'document',
    geoLevel: 'organization',
    districtId: null,
    districtName: null,
    period: '11507',
    periodStart: '2027-01-01',
    periodEnd: '2027-12-31',
    periodType: 'year',
    metricId: 'budget_amount',
    metricSource: 'metric_id',
    value: 220101,
    unit: 'TWD_thousand',
    ageScope: 'not_age_specific',
    youthEligibility: 'context_only',
    qualityFlags: [],
    sourcePath: 'curated/youth_budgets.json',
    computation: null,
    fetchedAt: '2026-09-12T02:10:43.554845+00:00',
  },
];

interface Scenario {
  label: string;
  expectation: string;
  run: (client: ReturnType<typeof createBedrockClientFromEnv>) => Promise<{ output: StructuredOutput }>;
}

const scenarios: Scenario[] = [
  {
    label: 'A. 問薪資，但只有人口與預算資料',
    expectation: 'dataSufficiency=insufficient，四塊全空',
    run: (client) =>
      dataQa(client, {
        question: '板橋區青年的平均薪資是多少？跟其他區比起來如何？',
        focusDistrict: '板橋區',
        focusArea: 'employment',
        evidence: populationOnly,
        knownLimitations: [],
        webFindings: [],
        webSearch: { enabled: false, contextSize: 'low', scope: 'all' },
      }),
  },
  {
    label: 'B. 問人口，資料有（但缺其他面向）',
    expectation: 'dataSufficiency=partial，且不可自行換算 budget 單位',
    run: (client) =>
      explainData(client, {
        question: null,
        focusDistrict: '板橋區',
        focusArea: 'population',
        evidence: populationOnly,
        knownLimitations: [],
        webFindings: [],
        webSearch: { enabled: false, contextSize: 'low', scope: 'all' },
      }),
  },
];

const client = createBedrockClientFromEnv();
if (client instanceof MockBedrockClient) {
  console.error('這支腳本要驗證真實模型的行為，Mock 沒有意義。請先設定好 .env。');
  process.exit(1);
}

console.log(`模型：${client.description}\n`);
let failures = 0;

for (const scenario of scenarios) {
  console.log('='.repeat(70));
  console.log(scenario.label);
  console.log(`預期：${scenario.expectation}`);
  console.log('='.repeat(70));

  const startedAt = Date.now();
  const { output } = await scenario.run(client);
  console.log(`耗時 ${Date.now() - startedAt} ms\n`);

  console.log('【第 1 步 盤點】');
  console.log(`  availableMetrics    : ${output.evidenceReview.availableMetrics.join(' | ')}`);
  console.log(`  youthSpecificMetrics: ${output.evidenceReview.youthSpecificMetrics.join(' | ')}`);
  console.log(`  contextOnlyMetrics  : ${output.evidenceReview.contextOnlyMetrics.join(' | ')}`);
  console.log(`  missingForQuestion  : ${output.evidenceReview.missingForQuestion.join(' | ')}`);
  console.log(`\n【第 2 步 充足度】${output.dataSufficiency}`);
  const conclusionCount =
    output.issues.length + output.strengths.length + output.resourceGaps.length + output.policyDirections.length;
  console.log(`【結論條數】${conclusionCount}（basis ${output.basis.length} 筆）`);

  if (conclusionCount > 0) {
    console.log('\n【內容】');
    for (const line of [...output.issues, ...output.strengths, ...output.resourceGaps, ...output.policyDirections]) {
      console.log(`  - ${line}`);
    }
  }
  console.log('\n【資料限制】');
  for (const line of output.limitations) {
    console.log(`  - ${line}`);
  }

  // 情境 A 是硬性期望：問了資料回答不了的東西，就必須說不知道。
  if (scenario.label.startsWith('A.')) {
    if (output.dataSufficiency !== 'insufficient') {
      console.error(`\n❌ 預期 insufficient，實際 ${output.dataSufficiency} —— prompt 還不夠強`);
      failures += 1;
    } else if (conclusionCount > 0) {
      console.error(`\n❌ 標了 insufficient 卻還是寫了 ${conclusionCount} 條結論`);
      failures += 1;
    } else {
      console.log('\n✅ 正確拒答');
    }
  }

  // 單位檢查：出現「萬千元」這種混用就是之前那個 bug。
  const allText = JSON.stringify(output);
  if (/萬千元|億千元/.test(allText)) {
    console.error('\n❌ 出現混用單位（萬千元／億千元），單位規則失效');
    failures += 1;
  }
  console.log();
}

console.log('='.repeat(70));
if (failures > 0) {
  console.error(`${failures} 項未通過`);
  process.exit(1);
}
console.log('全部通過');
