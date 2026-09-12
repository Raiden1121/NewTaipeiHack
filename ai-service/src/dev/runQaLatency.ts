/**
 * Q&A 延遲量測：`npm run dev:qa-latency`
 *
 * 跟 `dev:latency` 的差別：那支量的是 **Data Explanation**（沒有使用者問題，
 * 固定六塊輸出），這支量的是**實際會被使用者打到的 Q&A 問題形狀** ——
 * 從「純查值」到「為什麼 X 排第六」到「政策該怎麼做」，因為這三種問題的
 * 輸出量差了好幾倍，而延遲幾乎完全由輸出量決定。
 *
 * 為什麼要有這支腳本：之前每次換模型或改 prompt 都是臨時寫一支再刪掉，
 * 結果同一組數字沒辦法跨版本比較。這支固定情境，換模型只要重跑一次。
 *
 * 用法：
 *   npm run dev:qa-latency                    # 全部情境
 *   npm run dev:qa-latency -- --only=why      # 只跑「為什麼」類（最慢的那類）
 *   npm run dev:qa-latency -- --no-search     # 關掉網路搜尋，隔離出搜尋的成本
 *
 * 前置：data-pipeline 的 curated 與 analytics 快照要在本機（同 dev:analytics）。
 *
 * 輸出的每一行 SUMMARY 都是純 ASCII。理由很實際：Windows 的 PowerShell 把中文
 * 導向檔案時會弄壞相鄰位元組，實測「耗時：67245 ms」存檔後變成 `??嚗?7245 ms`，
 * 最前面那個數字直接消失，量到的數字無法回頭查證。
 */
import { createBedrockClientFromEnv, MockBedrockClient, type BedrockClient } from '../bedrock/client.js';
import {
  AnalyticsSnapshotEvidenceRepository,
  CompositeEvidenceRepository,
  CuratedFileEvidenceRepository,
  buildAiContext,
  defaultDataPipelineDataDir,
} from '../context/buildContext.js';
import { dataQa } from '../handlers/dataQa.js';
import { explainData } from '../handlers/explainData.js';
import { policyCopilot } from '../handlers/policyCopilot.js';
import { createWebSearchProviderFromEnv } from '../websearch/factory.js';
import { buildDataQaPrompt, QA_ANSWER_MAX_CHARS } from '../prompts/dataQa.js';
import { buildDataExplanationPrompt } from '../prompts/dataExplanation.js';
import { buildPolicyCopilotPrompt } from '../prompts/policyCopilot.js';
import type { AiRequestContext } from '../types/aiEvidence.js';
import type { AiFeatureResult } from '../handlers/runFeature.js';
import type { WebSearchSettings } from '../types/webFinding.js';
import type { PromptPayload } from '../prompts/promptPayload.js';

/** 粗估 token：CJK 約 1 token/字，其餘約 1 token/3.5 字元。 */
function estimateTokens(text: string): number {
  let cjk = 0;
  for (const char of text) {
    if (char.codePointAt(0)! > 0x2e80) {
      cjk += 1;
    }
  }
  return Math.round(cjk + (text.length - cjk) / 3.5);
}

const args = process.argv.slice(2);
const only = args.find((arg) => arg.startsWith('--only='))?.split('=')[1];
const noSearch = args.includes('--no-search');

const dataDir = process.env.AI_DATA_DIR ?? defaultDataPipelineDataDir();
const repository = new CompositeEvidenceRepository([
  new CuratedFileEvidenceRepository(dataDir),
  new AnalyticsSnapshotEvidenceRepository(dataDir, process.env.AI_ANALYTICS_SNAPSHOT_ID),
]);

const client: BedrockClient = createBedrockClientFromEnv();
if (client instanceof MockBedrockClient) {
  console.error('要量真實延遲，請先設定好 .env 的模型與 region。');
  process.exit(1);
}

/**
 * 搜尋 provider **必須自己建**，不能讓 handler 用預設值。
 *
 * 這是實測踩到的：handler 的 provider 參數是選填，沒傳就是
 * `DisabledWebSearchProvider`。第一版這支腳本沒傳，於是印著「網路搜尋：開啟」，
 * 量到的卻是**沒有搜尋**的延遲 —— 唯一的線索是 limitations 裡那句
 * 「已開啟上網搜尋，但沒有找到相關的網路資料」。
 * 正式路徑（`handlers/lambda.ts`）是有傳的，所以量測必須跟著傳，否則量的不是同一條路。
 */
const searchProvider = createWebSearchProviderFromEnv();

/** 關掉搜尋時用這組設定，用來隔離「搜尋佔了多少時間」。 */
const searchOff: WebSearchSettings = { enabled: false, contextSize: 'low', scope: 'all' };

interface Scenario {
  /** `--only=` 用的短名。 */
  key: string;
  label: string;
  district: string;
  area: string;
  /** null 代表沒有使用者問題（explain / policyCopilot 的情況）。 */
  question: string | null;
  feature: 'qa' | 'explain' | 'policy';
  /** 只有純查值情境會限制指標，用來對照「輸出量最小時的下限延遲」。 */
  metricIds?: readonly string[];
}

/**
 * 情境刻意照「輸出量由小到大」排，因為延遲幾乎跟輸出量成正比，
 * 這樣一眼就看得出成長曲線，而不是一堆散落的數字。
 */
const scenarios: Scenario[] = [
  {
    key: 'lookup',
    label: '1. 純查值（單一指標）',
    district: '板橋區',
    area: 'population',
    question: '板橋區有多少 18 到 35 歲的青年？',
    feature: 'qa',
    metricIds: ['youth_18_35_total'],
  },
  {
    key: 'small',
    label: '2. 單區小問題',
    district: '板橋區',
    area: 'employment',
    question: '板橋區青年的就業狀況如何？',
    feature: 'qa',
  },
  {
    key: 'why',
    label: '3. 為什麼類：八里薪資第六高',
    district: '八里區',
    area: 'employment',
    question: '為何八里的薪資中位數在新北市排第六高？',
    feature: 'qa',
  },
  {
    key: 'why',
    label: '4. 為什麼類：坪林薪資最高',
    district: '坪林區',
    area: 'employment',
    question: '為何坪林區的薪資中位數是新北市最高的？',
    feature: 'qa',
  },
  {
    key: 'policy',
    label: '5. 政策類問題',
    district: '板橋區',
    area: 'employment',
    question: '板橋區要提升青年留才，應該優先做什麼？',
    feature: 'qa',
  },
  {
    key: 'explain',
    label: '6. Data Explanation（無使用者問題）',
    district: '板橋區',
    area: 'employment',
    question: null,
    feature: 'explain',
  },
  {
    key: 'policyCopilot',
    label: '7. Policy Copilot（無使用者問題）',
    district: '板橋區',
    area: 'employment',
    question: null,
    feature: 'policy',
  },
];

interface Row {
  label: string;
  evidence: number;
  promptTokens: number;
  ms: number;
  answerChars: number;
  blocks: number;
  basis: number;
  webRefs: number;
  sufficiency: string;
  failed: boolean;
}

console.log(`模型：${client.description}`);
console.log(`evidence 來源：${repository.description}`);
console.log(`網路搜尋：${noSearch ? '關閉（--no-search）' : '開啟（預設）'}　provider=${searchProvider.description}`);
console.log('');

const rows: Row[] = [];

for (const scenario of scenarios) {
  if (only !== undefined && scenario.key !== only) {
    continue;
  }

  console.log('='.repeat(78));
  console.log(scenario.label);
  console.log('='.repeat(78));

  const context = await buildAiContext(repository, {
    focusDistrict: scenario.district,
    focusArea: scenario.area,
    ...(scenario.question === null ? {} : { question: scenario.question }),
    ...(scenario.metricIds === undefined ? {} : { metricIds: [...scenario.metricIds] }),
    ...(noSearch ? { webSearch: searchOff } : {}),
  });

  if (context.evidence.length === 0) {
    console.error('讀不到 evidence，請先確認 data-pipeline 的資料與 analytics 快照存在。');
    process.exit(1);
  }

  const request: AiRequestContext = { ...context, question: scenario.question };
  // prompt 要用**這個功能實際會送的那份**來量。
  // 不能一律用 Q&A 的：`buildDataQaPrompt` 會擋 `question === null`
  // （Q&A 沒有使用者問題就不該送），explain / policyCopilot 正是那種情況。
  const prompt = promptFor(scenario.feature, request);
  const promptTokens = estimateTokens(prompt.system) + estimateTokens(prompt.user);

  console.log(`evidence ${context.evidence.length} 筆　prompt≈${promptTokens} tok`);

  const startedAt = Date.now();
  let result: AiFeatureResult | null = null;
  let failure = '';
  try {
    result = await run(scenario.feature, request);
  } catch (error) {
    failure = error instanceof Error ? error.message : String(error);
  }
  const ms = Date.now() - startedAt;

  if (result === null) {
    console.log(`耗時 ${ms} ms —— 失敗：${failure}`);
    console.log(`SUMMARY key=${scenario.key} elapsedMs=${ms} result=FAILED`);
    console.log('');
    rows.push({
      label: scenario.label,
      evidence: context.evidence.length,
      promptTokens,
      ms,
      answerChars: 0,
      blocks: 0,
      basis: 0,
      webRefs: 0,
      sufficiency: 'FAILED',
      failed: true,
    });
    continue;
  }

  const { output } = result;
  const blocks =
    output.issues.length +
    output.strengths.length +
    output.resourceGaps.length +
    output.policyDirections.length;
  const answerChars = output.answer?.length ?? 0;

  // 字數上限是用 prompt 指示的（不是 schema 驗證，理由見 QA_ANSWER_MAX_CHARS 的註解），
  // 所以「有沒有遵守」必須實際量。沒量的話等於只是寫了一句願望。
  const capOk = scenario.feature !== 'qa' || answerChars <= QA_ANSWER_MAX_CHARS;

  console.log(`耗時 ${ms} ms`);
  console.log(
    `answer ${answerChars} 字${scenario.feature === 'qa' ? `（上限 ${QA_ANSWER_MAX_CHARS}${capOk ? ' OK' : ' 超出'}）` : ''}　` +
      `四塊 ${blocks} 條　basis ${output.basis.length} 筆　` +
      `webReferences ${output.webReferences.length} 筆　sufficiency=${output.dataSufficiency}`,
  );
  if (output.answer !== null) {
    console.log('');
    console.log(`【answer】${output.answer}`);
  }

  // 搜尋開著卻 webRefs=0 時，要能分辨「搜尋沒跑」和「跑了但模型沒引用」。
  // 這兩件事的處理方向完全不同，只看 webReferences 的筆數分不出來。
  const webSources = result.sources.filter((source) => source.kind === 'web');
  console.log('');
  console.log(`【網路來源】程式盤點到 ${webSources.length} 筆，模型引用 ${output.webReferences.length} 筆`);
  for (const source of webSources) {
    console.log(`  - ${source.url ?? source.recordUrls[0] ?? '(無網址)'}`);
  }
  console.log('【資料限制】');
  for (const line of output.limitations) {
    console.log(`  - ${line}`);
  }
  console.log('');
  console.log(
    `SUMMARY key=${scenario.key} elapsedMs=${ms} evidence=${context.evidence.length} ` +
      `promptTok=${promptTokens} answerChars=${answerChars} capOk=${capOk} blocks=${blocks} ` +
      `basis=${output.basis.length} webRefs=${output.webReferences.length} ` +
      `sufficiency=${output.dataSufficiency}`,
  );
  console.log('');

  rows.push({
    label: scenario.label,
    evidence: context.evidence.length,
    promptTokens,
    ms,
    answerChars,
    blocks,
    basis: output.basis.length,
    webRefs: output.webReferences.length,
    sufficiency: output.dataSufficiency,
    failed: false,
  });
}

console.log('='.repeat(78));
console.log('TABLE label|evidence|promptTok|ms|answerChars|blocks|basis|sufficiency');
for (const row of rows) {
  console.log(
    `TABLE ${row.label.replace(/[|]/g, '/')}|${row.evidence}|${row.promptTokens}|${row.ms}|` +
      `${row.answerChars}|${row.blocks}|${row.basis}|${row.sufficiency}`,
  );
}

// API Gateway 的整合逾時是真正的天花板：HTTP API 固定 30 秒不可調。
const usable = rows.filter((row) => !row.failed);
if (usable.length > 0) {
  const worst = Math.max(...usable.map((row) => row.ms));
  const over = usable.filter((row) => row.ms > 29_000);
  console.log(`SUMMARY_TOTAL scenarios=${usable.length} worstMs=${worst} over29s=${over.length}`);
  if (over.length > 0) {
    console.log(`OVER_LIMIT ${over.map((row) => `${row.label}=${row.ms}ms`).join(' ; ')}`);
  }
}

function promptFor(feature: Scenario['feature'], request: AiRequestContext): PromptPayload {
  if (feature === 'qa') {
    return buildDataQaPrompt(request);
  }
  if (feature === 'policy') {
    return buildPolicyCopilotPrompt(request);
  }
  return buildDataExplanationPrompt(request);
}

async function run(
  feature: Scenario['feature'],
  request: AiRequestContext,
): Promise<AiFeatureResult> {
  if (feature === 'qa') {
    return dataQa(client, request, searchProvider);
  }
  if (feature === 'policy') {
    return policyCopilot(client, request, searchProvider);
  }
  return explainData(client, request, searchProvider);
}
