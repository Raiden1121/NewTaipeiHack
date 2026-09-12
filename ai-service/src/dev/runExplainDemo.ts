/**
 * 本機 demo：`npm run dev:explain`
 *
 * 用 **data-pipeline 真的產生出來的 curated 資料**跑完整條路徑：
 * dataset_index → curated 檔案 → evidence → prompt → Bedrock（或 Mock）→ 六塊輸出。
 *
 * 這支腳本刻意讀真實檔案而不是手寫 fixture，因為「格式對不上」這種問題只有接真實
 * 資料才會現形（實測就抓到 7 個 dataset 的 metric_id / value 全是 null）。
 *
 * 前置：先在 data-pipeline 產生本機資料，否則會看到清楚的錯誤訊息告訴你要跑什麼：
 *   cd data-pipeline
 *   python src/run_pipeline.py --period 11507 --output-dir data
 *
 * 沒設 AWS_REGION / BEDROCK_MODEL_ID 時會自動用 MockBedrockClient，不需要 AWS 也能跑。
 */
import { createBedrockClientFromEnv } from '../bedrock/client.js';
import { buildAiContext, createEvidenceRepositoryFromEnv } from '../context/buildContext.js';
import { explainData } from '../handlers/explainData.js';
import { formatSourceAttributions } from '../types/sourceAttribution.js';

const repository = createEvidenceRepositoryFromEnv();
const client = createBedrockClientFromEnv();

const focusDistrict = process.argv[2] ?? '板橋區';

const context = await buildAiContext(repository, {
  focusDistrict,
  focusArea: 'employment',
  // 只取 long-form dataset：這 4 個的 metric_id / value 是 pipeline 直接填好的，
  // 不需要任何彙總就有解讀價值。house_prices / rentals 由 repository 預設排除。
  datasets: ['population', 'movement', 'vt_courses', 'youth_budgets'],
  limitPerDataset: 40,
});

console.log(`evidence 來源：${repository.description}`);
console.log(`模型：${client.description}`);
console.log(`行政區：${focusDistrict}`);
console.log(`evidence 筆數：${context.evidence.length}`);
console.log(`既知限制：${context.knownLimitations.length} 條`);
console.log('---');

if (context.evidence.length > 0) {
  console.log('前 3 筆 evidence：');
  for (const item of context.evidence.slice(0, 3)) {
    console.log(
      `  ${item.evidenceId} | ${item.districtName ?? item.geoLevel} | ${item.metricId}=${item.value} ${item.unit ?? ''} | youthEligibility=${item.youthEligibility}`,
    );
  }
  console.log('---');
}

const { output, sources } = await explainData(client, context);

console.log('資料來源（程式從被引用的 evidence 推導，非模型產生）：');
console.log(formatSourceAttributions(sources));
console.log('---');
console.log(JSON.stringify({ output, sources }, null, 2));
