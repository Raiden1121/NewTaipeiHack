/**
 * 拿到 AWS 權限、填好 .env 之後的第一個 smoke test：`npm run dev:bedrock-smoke`
 *
 * 刻意跳過 context builder 與真實資料，只驗「Bedrock 打得通」這一件事。
 * 這樣如果失敗，你就知道問題一定在權限／region／model access，跟資料格式無關。
 * 計畫書的時間盒說這一步卡超過 1 小時就要去找隊友要權限——所以它要能單獨跑。
 *
 * 執行前確認三件事：
 * 1. `ai-service/.env` 裡 `AWS_REGION`、`BEDROCK_MODEL_ID` 都填了（見 `.env.example`）。
 * 2. 這個 shell 有可用的 AWS 憑證（`aws configure` 設過，或匯出了
 *    `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` / `AWS_SESSION_TOKEN`）。
 * 3. 已經在 Bedrock 主控台的 Model access 把 `BEDROCK_MODEL_ID` 對應的模型打開。
 *    這步沒做，呼叫一定會回 AccessDeniedException。
 *
 * 常見錯誤對照：
 * - `AccessDeniedException` → 第 3 點沒做，或 IAM 少了 `bedrock:InvokeModel`
 * - `ValidationException` 提到 model identifier → model ID 拼錯，或該 region 沒有這個模型；
 *   跨區模型要用 inference profile ID（例如 `us.` 開頭）而不是裸的 model ID
 * - `ValidationException` 提到 outputConfig / schema → 這個模型不支援原生 structured
 *   outputs，先設 `BEDROCK_STRUCTURED_OUTPUT=off` 再跑
 * - `UnrecognizedClientException` → 憑證無效或過期（SSO / session token 要重新取得）
 */
import { createBedrockClientFromEnv, MockBedrockClient } from '../bedrock/client.js';
import { describeEnvProblems, resolveBedrockEnv } from '../bedrock/env.js';
import { explainData } from '../handlers/explainData.js';
import type { AiRequestContext } from '../types/aiEvidence.js';
import { formatSourceAttributions } from '../types/sourceAttribution.js';

/**
 * 一筆最小的 evidence。用 population 的 `youth_18_35_total` 是刻意的：
 * 它是真實資料裡唯一 `youthEligibility === 'eligible'` 的指標，可以順便確認
 * 模型有沒有正確處理青年核心資料的語意。
 */
const smokeContext: AiRequestContext = {
  question: null,
  focusDistrict: '板橋區',
  focusArea: 'population',
  evidence: [
    {
      evidenceId: 'population:11507:0:youth_18_35_total',
      dataset: 'population',
      source: 'moi_household_registration',
      sourceRecordId: 'population:65000010:2026-07',
      geoLevel: 'district',
      districtId: '65000010',
      districtName: '板橋區',
      period: '11507',
      periodStart: '2026-07-01',
      periodEnd: '2026-07-31',
      periodType: 'month',
      metricId: 'youth_18_35_total',
      metricSource: 'metric_id',
      // 真實值：取自 data-pipeline 實際輸出的 curated/population.json
      // （板橋區 youth_18_35_male 54892 + youth_18_35_female 51581）。
      // 這支腳本裡的每個值都必須是真的 —— 叫 smoke test 的東西放假數字，
      // 遲早會有人拿它當真。
      value: 106473,
      unit: 'people',
      ageScope: 'derived_18_35',
      youthEligibility: 'eligible',
      qualityFlags: [],
      sourcePath: 'curated/population.json',
      computation: null,
      sourceUrl: null,
      sourceKind: 'dataset',
      fetchedAt: '2026-09-12T01:56:04.525401+00:00',
    },
  ],
  knownLimitations: [
    '這是 Bedrock 連線測試，只餵了一筆人口指標，不涵蓋就業、居住或資源面向。',
  ],
  webFindings: [],
  webSearch: { enabled: false, contextSize: 'low' },
};

const envConfig = resolveBedrockEnv();
console.log('環境變數解析結果：');
console.log(`  模型      ${envConfig.modelId ?? '(未設定)'}  ← ${envConfig.resolvedFrom.modelId ?? 'n/a'}`);
console.log(`  region    ${envConfig.region ?? '(未設定)'}  ← ${envConfig.resolvedFrom.region ?? 'n/a'}`);
console.log(
  `  認證      ${envConfig.authMode}${envConfig.apiKey ? `（API key 來自 ${envConfig.resolvedFrom.apiKey}）` : ''}`,
);

const problems = describeEnvProblems(envConfig);
if (problems.length > 0) {
  console.warn('\n設定看起來有問題：');
  for (const problem of problems) {
    console.warn(`  - ${problem}`);
  }
}

const client = createBedrockClientFromEnv();

if (client instanceof MockBedrockClient) {
  console.error(
    '\n目前還是 MockBedrockClient，代表模型或 region 沒讀到。\n' +
      '這支腳本會讀 <repo>/.env 與 ai-service/.env（後者覆寫前者）。',
  );
  process.exit(1);
}

console.log(`\n呼叫 ${client.description} ...`);
const startedAt = Date.now();

try {
  const { output, sources } = await explainData(client, smokeContext);
  console.log(`成功，耗時 ${Date.now() - startedAt} ms`);
  console.log(`dataSufficiency=${output.dataSufficiency}`);
  console.log(`basis 引用了 ${output.basis.length} 筆 evidence`);
  console.log('\n資料來源（程式從被引用的 evidence 推導，非模型產生）：');
  console.log(formatSourceAttributions(sources));
  console.log('\n完整輸出：');
  console.log(JSON.stringify({ output, sources }, null, 2));
} catch (error) {
  console.error(`失敗，耗時 ${Date.now() - startedAt} ms`);
  console.error(error instanceof Error ? `${error.name}: ${error.message}` : String(error));
  console.error('\n請對照本檔案開頭的「常見錯誤對照」排查。');
  process.exit(1);
}
