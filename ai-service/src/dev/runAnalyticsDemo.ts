/**
 * 本機 demo：`npm run dev:analytics`
 *
 * 跑通 **analytics published snapshot → evidence → prompt → 六塊輸出** 這條路徑。
 *
 * 跟 `dev:explain` 的差別：那支驗的是 curated（原始資料點），這支驗的是
 * **Deterministic Analytics 算完的複合指標**（Youth Opportunity Index、各區房價
 * 中位數、留才風險等級、生育率、服務涵蓋率…）。這些指標才是回答「哪一區的青年
 * 發展機會較好」「哪一區有留才風險」這類核心問題唯一能引用的東西 ——
 * 在這條路徑接上之前，那些數字早就算好了，只是躺在快照裡沒有人讀。
 *
 * 前置：data-pipeline 要先產生並發布 analytics 快照，否則會看到清楚的錯誤訊息。
 * 檢查方式：`data-pipeline/data/analytics/published/current.json` 存在且指到一個
 * 有 `manifest.json` 的目錄。
 *
 * 用法：
 *   npm run dev:analytics                      # 板橋區、employment 主題、跑三個功能
 *   npm run dev:analytics -- 三重區 fertility   # 指定行政區與主題
 *   npm run dev:analytics -- 板橋區 employment --mock   # 強制用 Mock，不打 Bedrock
 *   npm run dev:analytics -- --dry               # 只看 context 與 prompt 成本，不呼叫模型
 *
 * 沒設 AWS_REGION / BEDROCK_MODEL_ID 時會自動用 MockBedrockClient。
 */
import { createBedrockClientFromEnv, MockBedrockClient, type BedrockClient } from '../bedrock/client.js';
import {
  AnalyticsSnapshotEvidenceRepository,
  CompositeEvidenceRepository,
  CuratedFileEvidenceRepository,
  buildAiContext,
  defaultDataPipelineDataDir,
  readAnalyticsSnapshot,
} from '../context/buildContext.js';
import { dataQa } from '../handlers/dataQa.js';
import { explainData } from '../handlers/explainData.js';
import { policyCopilot } from '../handlers/policyCopilot.js';
import { formatEvidenceForPrompt } from '../prompts/guardrails.js';
import { formatSourceAttributions } from '../types/sourceAttribution.js';
import type { AiRequestContext } from '../types/aiEvidence.js';
import type { AiFeatureResult } from '../handlers/runFeature.js';

const args = process.argv.slice(2);
const flags = new Set(args.filter((arg) => arg.startsWith('--')));
const positional = args.filter((arg) => !arg.startsWith('--'));

const focusDistrict = positional[0] ?? '板橋區';
const focusArea = positional[1] ?? 'employment';
const dryRun = flags.has('--dry');
const forceMock = flags.has('--mock');

const dataDir = process.env.AI_DATA_DIR ?? defaultDataPipelineDataDir();

// 先把快照本身印出來。這一步失敗就不用往下走了，而且錯誤訊息會直接說要跑什麼。
const snapshot = await readAnalyticsSnapshot(dataDir, process.env.AI_ANALYTICS_SNAPSHOT_ID);
console.log('=== analytics snapshot ===');
console.log(`snapshot_id     : ${snapshot.snapshotId}`);
console.log(`generated_at    : ${snapshot.generatedAt ?? '(無)'}`);
console.log(`schema_version  : ${snapshot.schemaVersion ?? '(無)'}`);
console.log(`artifacts       : ${snapshot.artifacts.map((item) => item.key).join(', ')}`);
console.log(`upstream        : ${snapshot.upstreamDatasets.join(', ') || '(無)'}`);
console.log(`warnings        : ${snapshot.warnings.join(', ') || '(無)'}`);
console.log('');

// 刻意用 Composite 而不是只用 analytics：這支腳本要驗的是「兩種來源併起來不會打架」，
// 尤其是 metricSource 的區分，以及居住負擔那條限制有沒有被正確換掉。
const repository = new CompositeEvidenceRepository([
  new CuratedFileEvidenceRepository(dataDir),
  new AnalyticsSnapshotEvidenceRepository(dataDir, process.env.AI_ANALYTICS_SNAPSHOT_ID),
]);

const context = await buildAiContext(repository, { focusDistrict, focusArea });

report(context);

if (dryRun) {
  console.log('--dry：不呼叫模型，結束。');
  process.exit(0);
}

const client: BedrockClient = forceMock ? new MockBedrockClient() : createBedrockClientFromEnv();
console.log(`模型：${client.description}`);
console.log('');

// `--feature=explain|policy|qa` 只跑其中一個。Opus 一次要 40 秒以上，三個一起跑
// 很容易撞到外層的執行時間上限，隔開來跑才問得出「到底是哪一個失敗」。
const only = args.find((arg) => arg.startsWith('--feature='))?.split('=')[1];
const shouldRun = (name: string): boolean => only === undefined || only === name;

if (shouldRun('explain')) {
  await runFeature('Data Explanation', () => explainData(client, context));
}
if (shouldRun('policy')) {
  await runFeature('AI Policy Copilot', () => policyCopilot(client, context));
}
if (shouldRun('qa')) {
  await runFeature('AI Data Q&A', () =>
    dataQa(client, {
      ...context,
      question: `${focusDistrict}的青年發展機會和留才風險，跟新北市其他行政區比起來如何？`,
    }),
  );
}

function report(context: AiRequestContext): void {
  const analytics = context.evidence.filter((item) => item.metricSource === 'analytics_metric');
  const curated = context.evidence.filter((item) => item.metricSource !== 'analytics_metric');
  const prompt = formatEvidenceForPrompt(context.evidence);

  console.log('=== context ===');
  console.log(`evidence 來源   : ${repository.description}`);
  console.log(`行政區／主題    : ${focusDistrict} / ${focusArea}`);
  console.log(`evidence 筆數   : ${context.evidence.length}`);
  console.log(`  analytics_metric（彙總指標）: ${analytics.length}`);
  console.log(`  curated（原始資料點）        : ${curated.length}`);
  console.log(`evidence prompt : ${prompt.length} 字元（約 ${Math.round(prompt.length / 3)} token）`);
  console.log(`既知限制        : ${context.knownLimitations.length} 條`);
  console.log('');

  // 挑幾個最關鍵的複合指標印出來，這樣一眼就看得出「數字真的進來了」。
  const highlights = [
    'opportunityIndex',
    'retentionRiskLevel',
    'house_price_median',
    'rent_median',
    'fertilityRate',
    'serviceCoverageRate',
    'youth_18_35_total',
  ];
  console.log('=== 關鍵複合指標（本次是否讀到）===');
  for (const metricId of highlights) {
    const hit = analytics.find(
      (item) => item.metricId === metricId && item.districtName === focusDistrict,
    );
    if (hit === undefined) {
      console.log(`  ${metricId.padEnd(22)} : (本次未讀到)`);
      continue;
    }
    console.log(
      `  ${metricId.padEnd(22)} : ${hit.value} ${hit.unit ?? ''}  [${hit.youthEligibility}]  ${hit.computation ?? ''}`,
    );
  }
  console.log('');

  console.log('=== 既知限制（會原封不動進到輸出的 limitations）===');
  for (const note of context.knownLimitations) {
    console.log(`  - ${note}`);
  }
  console.log('');
}

async function runFeature(label: string, run: () => Promise<AiFeatureResult>): Promise<void> {
  console.log(`########## ${label} ##########`);
  const startedAt = Date.now();
  try {
    const { output, sources } = await run();
    const elapsed = Date.now() - startedAt;

    console.log(`耗時：${elapsed} ms`);
    console.log(`dataSufficiency：${output.dataSufficiency}`);
    console.log(
      `六塊：issues=${output.issues.length} strengths=${output.strengths.length} ` +
        `resourceGaps=${output.resourceGaps.length} policyDirections=${output.policyDirections.length} ` +
        `basis=${output.basis.length} limitations=${output.limitations.length}`,
    );

    // 這是最重要的檢查：模型有沒有真的引用到 analytics 的彙總指標。
    // 只要 basis 裡沒有一筆 analytics_metric，就代表複合指標白給了。
    const analyticsIds = new Set(
      context.evidence
        .filter((item) => item.metricSource === 'analytics_metric')
        .map((item) => item.evidenceId),
    );
    const citedAnalytics = output.basis.filter((citation) => analyticsIds.has(citation.evidenceId));
    console.log(`basis 引用到的彙總指標：${citedAnalytics.length} / ${output.basis.length} 筆`);
    for (const citation of citedAnalytics.slice(0, 5)) {
      console.log(`  - ${citation.evidenceId}`);
      console.log(`    ${citation.note}`);
    }

    console.log('資料來源（程式推導，非模型產生）：');
    console.log(formatSourceAttributions(sources));

    // 純 ASCII 的摘要行。
    // 理由很實際：Windows 的 PowerShell 在把中文輸出導向檔案時會弄壞相鄰的位元組，
    // 實測「耗時：67245 ms」存進檔案後變成 `??嚗?7245 ms` —— 最前面那個數字直接消失，
    // 於是量到的延遲數字無法回頭查證。關鍵數字用 ASCII 再輸出一次就不會有這個問題。
    console.log(
      `SUMMARY feature=${label.replace(/\s+/g, '_')} elapsedMs=${elapsed} ` +
        `dataSufficiency=${output.dataSufficiency} evidence=${context.evidence.length} ` +
        `basis=${output.basis.length} analyticsCited=${citedAnalytics.length} ` +
        `limitations=${output.limitations.length} sources=${sources.length}`,
    );
    console.log('');
  } catch (error) {
    console.log(`失敗：${error instanceof Error ? error.message : String(error)}`);
    console.log(`SUMMARY feature=${label.replace(/\s+/g, '_')} result=FAILED`);
    console.log('');
  }
}
