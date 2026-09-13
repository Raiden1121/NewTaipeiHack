/**
 * 檢查 DynamoDB 的 analytics 表讀不讀得到：`npm run dev:dynamo-check`
 *
 * 不呼叫模型，只驗證「憑證 → 表 → item → evidence」這條鏈路。
 * 部署前應該先跑這一支，再跑 `dev:ask`。
 *
 * 用法：
 *   $env:ANALYTICS_TABLE_NAME="newtaipei-youth-analytics"
 *   npm run dev:dynamo-check
 *   npm run dev:dynamo-check -- 板橋區 employment
 *
 * 會印出：實際讀到哪些 item、產生幾筆 evidence、跟本機快照的差異。
 * **跟快照比對是重點** —— 兩邊的 metricId 應該一致，不一致就代表
 * 切換來源會讓預先算的 fingerprint 失效、prompt 也會長得不一樣。
 */
import {
  AnalyticsSnapshotEvidenceRepository,
  DynamoEvidenceRepository,
  defaultDataPipelineDataDir,
} from '../context/buildContext.js';

const positional = process.argv.slice(2).filter((arg) => !arg.startsWith('--'));
const focusDistrict = positional[0] ?? '板橋區';
const focusArea = positional[1] ?? 'employment';

const tableName = process.env.ANALYTICS_TABLE_NAME?.trim();
if (tableName === undefined || tableName === '') {
  console.error(
    '沒有設 ANALYTICS_TABLE_NAME。\n' +
      '例如：$env:ANALYTICS_TABLE_NAME="newtaipei-youth-analytics"\n' +
      '表名是 Terraform 的 module.analytics_table 建的（{project_name}-analytics）。',
  );
  process.exit(1);
}

const region =
  process.env.BEDROCK_REGION ?? process.env.AWS_REGION ?? process.env.AWS_DEFAULT_REGION;
console.log(`表      : ${tableName}`);
console.log(`region  : ${region ?? '(用 SDK 預設)'}`);
console.log(`行政區  : ${focusDistrict}　主題：${focusArea}`);
console.log('');

const dynamo = new DynamoEvidenceRepository({
  tableName,
  ...(region === undefined ? {} : { region }),
});

const startedAt = Date.now();
let bundle;
try {
  bundle = await dynamo.query({ focusArea, districtNames: [focusDistrict], limitPerDataset: 100_000 });
} catch (error) {
  const message = error instanceof Error ? error.message : String(error);
  console.error(`❌ 讀取失敗：${message}`);
  if (/credential|token|security/i.test(message)) {
    console.error(
      '\n看起來是憑證問題。這支腳本走 AWS SigV4（不是 Bedrock 的 bearer token），' +
        '所以 BEDROCK_AUTH=bearer 對它沒有用。\n' +
        '需要有效的 AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY（＋臨時憑證的 AWS_SESSION_TOKEN），' +
        '或設好的 AWS_PROFILE。',
    );
  }
  if (/ResourceNotFound/i.test(message)) {
    console.error('\n表不存在。確認 terraform apply 跑過，以及表名與 region 是否正確。');
  }
  process.exit(1);
}

console.log(`讀取耗時: ${Date.now() - startedAt} ms`);
console.log(`evidence : ${bundle.evidence.length} 筆（totalMatched ${bundle.totalMatched}）`);
console.log('');

if (bundle.evidence.length === 0) {
  console.log('⚠️ 沒有讀到任何 evidence。notes：');
  for (const note of bundle.notes) {
    console.log(`  - ${note}`);
  }
  console.log('');
  console.log('表是空的話，要先讓 data-pipeline（或 infrastructure/scripts/seed_test_data.py）寫入。');
  process.exit(1);
}

const byDistrict = new Map<string, number>();
for (const item of bundle.evidence) {
  const key = item.districtName ?? `(${item.geoLevel ?? 'n/a'})`;
  byDistrict.set(key, (byDistrict.get(key) ?? 0) + 1);
}
console.log('各行政區的 evidence 筆數（前 8）：');
for (const [name, count] of [...byDistrict.entries()].sort((a, b) => b[1] - a[1]).slice(0, 8)) {
  console.log(`  ${name.padEnd(10)} ${count}`);
}

console.log('');
console.log('前 5 筆 evidence：');
for (const item of bundle.evidence.slice(0, 5)) {
  console.log(`  ${item.evidenceId}`);
  console.log(`    value=${item.value} unit=${item.unit ?? 'null'} elig=${item.youthEligibility ?? 'null'}`);
}

// ---------------------------------------------------------------------------
// 跟本機快照比對 metricId
//
// 兩邊必須一致，否則切換來源時：預先算的 fingerprint 全部失效（每次 miss →
// 即時算 50 秒）、prompt 內容改變、關鍵字表對不上指標。
// ---------------------------------------------------------------------------
console.log('');
console.log('='.repeat(78));
console.log('跟本機 analytics 快照比對 metricId');
console.log('='.repeat(78));
try {
  const snapshot = new AnalyticsSnapshotEvidenceRepository(
    process.env.AI_DATA_DIR ?? defaultDataPipelineDataDir(),
    process.env.AI_ANALYTICS_SNAPSHOT_ID,
  );
  const local = await snapshot.query({
    focusArea,
    districtNames: [focusDistrict],
    limitPerDataset: 100_000,
  });

  const dynamoMetrics = new Set(bundle.evidence.map((item) => item.metricId.split('#')[0]!));
  const localMetrics = new Set(local.evidence.map((item) => item.metricId.split('#')[0]!));
  const onlyDynamo = [...dynamoMetrics].filter((metricId) => !localMetrics.has(metricId)).sort();
  const onlyLocal = [...localMetrics].filter((metricId) => !dynamoMetrics.has(metricId)).sort();

  console.log(`DynamoDB : ${dynamoMetrics.size} 種指標`);
  console.log(`本機快照 : ${localMetrics.size} 種指標`);
  console.log(`只在 DynamoDB: ${onlyDynamo.length}`);
  console.log(`只在本機快照 : ${onlyLocal.length}`);
  if (onlyDynamo.length > 0) {
    console.log(`  只在 DynamoDB: ${onlyDynamo.slice(0, 20).join(', ')}`);
  }
  if (onlyLocal.length > 0) {
    console.log(`  只在本機快照: ${onlyLocal.slice(0, 20).join(', ')}`);
  }
  console.log('');
  console.log(
    `SUMMARY table=${tableName} evidence=${bundle.evidence.length} ` +
      `dynamoMetrics=${dynamoMetrics.size} localMetrics=${localMetrics.size} ` +
      `onlyDynamo=${onlyDynamo.length} onlyLocal=${onlyLocal.length}`,
  );
} catch (error) {
  console.log(
    `（讀不到本機快照，跳過比對：${error instanceof Error ? error.message : String(error)}）`,
  );
  console.log(`SUMMARY table=${tableName} evidence=${bundle.evidence.length}`);
}
