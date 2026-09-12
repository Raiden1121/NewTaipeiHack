/**
 * 延遲量測：`npm run dev:latency`
 *
 * 為什麼需要這支腳本：之前的延遲數字（15s、17.6s、25.7s）全部是用**硬寫在原始碼裡的
 * 1–2 筆 evidence** 量的，而真實一個行政區會有 60 筆以上。拿小 prompt 的數字去推論
 * 「API Gateway 會不會超時」方向是錯的 —— 真實情況只會更慢。
 *
 * 這支腳本用 **data-pipeline 真的產出的 curated 資料**，量不同 evidence 筆數下的延遲，
 * 並印出 prompt 大小，讓「該不該換模型 / 該不該限制筆數」有數據可依據。
 *
 * 前置：先產生本機資料
 *   cd data-pipeline && python src/run_pipeline.py --period 11507 --output-dir data
 */
import { createBedrockClientFromEnv, MockBedrockClient } from '../bedrock/client.js';
import { buildAiContext, createEvidenceRepositoryFromEnv } from '../context/buildContext.js';
import { buildDataExplanationPrompt } from '../prompts/dataExplanation.js';
import { explainData } from '../handlers/explainData.js';

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

const repository = createEvidenceRepositoryFromEnv();
const client = createBedrockClientFromEnv();

if (client instanceof MockBedrockClient) {
  console.error('要量真實延遲，請先設定好 .env 的模型與 region。');
  process.exit(1);
}

console.log(`模型：${client.description}`);
console.log(`evidence 來源：${repository.description}\n`);

/**
 * 三種規模：
 * - 1 筆   ：對照之前那些「硬寫 1 筆」的數字
 * - 20 筆  ：假設之後決定限制筆數
 * - 不限   ：真實一個行政區的全部（實測板橋區 64 筆），這才是要拿去推論超時風險的數字
 */
const scenarios: { label: string; limitPerDataset?: number }[] = [
  { label: '1 筆（對照舊數字）', limitPerDataset: 1 },
  { label: '20 筆', limitPerDataset: 20 },
  { label: '不限（真實全量）' },
];

const rows: { label: string; evidence: number; promptTokens: number; ms: number; outputs: number }[] = [];

for (const scenario of scenarios) {
  const context = await buildAiContext(repository, {
    focusDistrict: '板橋區',
    focusArea: 'population',
    datasets: ['population', 'movement', 'vt_courses', 'youth_budgets'],
    ...(scenario.limitPerDataset === undefined ? {} : { limitPerDataset: scenario.limitPerDataset }),
  });

  if (context.evidence.length === 0) {
    console.error(
      '讀不到 evidence。請先執行：cd data-pipeline && python src/run_pipeline.py --period 11507 --output-dir data',
    );
    process.exit(1);
  }

  // 量 prompt 大小：system 幾乎固定（規則＋範例），user 隨 evidence 筆數變動。
  const prompt = buildDataExplanationPrompt({ ...context, evidence: context.evidence });
  const promptTokens = estimateTokens(prompt.system) + estimateTokens(prompt.user);

  const startedAt = Date.now();
  const { output } = await explainData(client, context);
  const ms = Date.now() - startedAt;

  const outputs =
    output.issues.length +
    output.strengths.length +
    output.resourceGaps.length +
    output.policyDirections.length;

  rows.push({ label: scenario.label, evidence: context.evidence.length, promptTokens, ms, outputs });

  console.log(
    `${scenario.label.padEnd(20)} evidence=${String(context.evidence.length).padStart(3)}  ` +
      `prompt≈${String(promptTokens).padStart(6)} tok  ` +
      `耗時=${String(ms).padStart(6)} ms  ` +
      `結論=${outputs} 條  sufficiency=${output.dataSufficiency}`,
  );
}

console.log(`\n${'='.repeat(78)}`);
console.log('label'.padEnd(20) + 'evidence'.padStart(10) + 'prompt_tok'.padStart(12) + 'ms'.padStart(9) + '結論'.padStart(8));
console.log('-'.repeat(78));
for (const row of rows) {
  console.log(
    row.label.padEnd(20) +
      String(row.evidence).padStart(10) +
      String(row.promptTokens).padStart(12) +
      String(row.ms).padStart(9) +
      String(row.outputs).padStart(8),
  );
}

// API Gateway 的整合逾時是真正的天花板：HTTP API 固定 30 秒，
// REST API 預設 29 秒（Regional/private 可申請調高）。
const worst = Math.max(...rows.map((row) => row.ms));
console.log(`\n最慢 ${worst} ms`);
if (worst > 29_000) {
  console.error('❌ 已超過 API Gateway 的 29/30 秒上限 —— 必須換小模型、限制 evidence 筆數，或改用 Function URL。');
} else if (worst > 20_000) {
  console.warn('⚠️ 已超過 20 秒，加上冷啟動就可能撞破 API Gateway 上限。');
} else {
  console.log('在 API Gateway 上限內（仍要保留冷啟動餘裕）。');
}
