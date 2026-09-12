/**
 * 稽核 `ANALYTICS_METRIC_META` 對快照的覆蓋率：`npm run dev:metric-audit`
 *
 * ## 為什麼需要這支
 *
 * analytics 快照**沒有** `unit` / `youth_eligibility` / `age_scope` 欄位
 * （實測 8 個 artifact 全部沒有），所以這三件事只能靠 `ANALYTICS_METRIC_META`
 * 這張手寫的對照表。
 *
 * 那張表的問題是它會**默默過期**：data-pipeline 新增指標時，指標會自動被納入
 * evidence，但單位變成 `null`、青年適用性退回名稱規則（`inferMeta`）。
 * 不會有編譯錯誤，不會有測試失敗，只會讓模型少了單位資訊 ——
 * 而單位錯誤是實測踩過的（把 220,101 千元講成「2 億 2,010 萬千元」）。
 *
 * 這支腳本用**實際產生出來的 evidence** 來稽核，不是數 JSON 葉欄位
 * （後者會高估問題：`villages` / `normalizedInputs` / `points` / `time_policy`
 * 早就被 `BLOCKED_KEYS` 擋掉，`year_roc` / `stage` 也在 `METADATA_KEYS` 裡）。
 *
 * 用法：
 *   npm run dev:metric-audit                 # 全部 artifact
 *   npm run dev:metric-audit -- employment   # 只看某個主題
 *   npm run dev:metric-audit -- --strict     # 有缺就 exit 1（可放進 CI）
 *
 * 不呼叫模型，不花任何 Bedrock 額度。
 */
import {
  AnalyticsSnapshotEvidenceRepository,
  ANALYTICS_METRIC_META,
  defaultDataPipelineDataDir,
  readAnalyticsSnapshot,
} from '../context/buildContext.js';
import type { AiEvidence } from '../types/aiEvidence.js';

const args = process.argv.slice(2);
const strict = args.includes('--strict');
const focusArea = args.find((arg) => !arg.startsWith('--')) ?? null;

const dataDir = process.env.AI_DATA_DIR ?? defaultDataPipelineDataDir();
const snapshotId = process.env.AI_ANALYTICS_SNAPSHOT_ID;

const snapshot = await readAnalyticsSnapshot(dataDir, snapshotId);
const repository = new AnalyticsSnapshotEvidenceRepository(dataDir, snapshotId);

// 刻意不篩行政區、把上限開到很大：要看的是「這份快照能產生的所有指標」，
// 而不是某一次請求拿到的子集。
const bundle = await repository.query({
  ...(focusArea === null ? {} : { focusArea }),
  limitPerDataset: 100_000,
});

interface MetricRow {
  metricId: string;
  count: number;
  unit: string | null;
  youthEligibility: string | null;
  sample: AiEvidence['value'];
  datasets: Set<string>;
}

const rows = new Map<string, MetricRow>();
for (const item of bundle.evidence) {
  // metricId 可能帶 `#識別字`（keywords[].weight#居住正義），稽核要看的是前面那段。
  const base = item.metricId.split('#')[0]!;
  const row = rows.get(base) ?? {
    metricId: base,
    count: 0,
    unit: item.unit,
    youthEligibility: item.youthEligibility,
    sample: item.value,
    datasets: new Set<string>(),
  };
  row.count += 1;
  row.datasets.add(item.dataset);
  rows.set(base, row);
}

// 對照表的 key 是**葉欄位名稱**，而 metricId 可能是 `a.b.c` 的路徑形式，
// 所以比對要用最後一段。
const metaKeys = new Set(Object.keys(ANALYTICS_METRIC_META));
const leafOf = (metricId: string): string => metricId.split('.').pop() ?? metricId;

const all = [...rows.values()].sort((left, right) => right.count - left.count);
const missing = all.filter((row) => !metaKeys.has(leafOf(row.metricId)));
const noUnit = all.filter((row) => row.unit === null);

console.log(`快照        : ${snapshot.snapshotId}`);
console.log(`主題        : ${focusArea ?? '(全部)'}`);
console.log(`evidence    : ${bundle.evidence.length} 筆（totalMatched ${bundle.totalMatched}）`);
console.log(`指標種類    : ${all.length}`);
console.log(`對照表 key  : ${metaKeys.size}`);
console.log('');
console.log(`不在對照表  : ${missing.length} 種  ← 這些走 inferMeta() 的名稱規則`);
console.log(`unit 是 null: ${noUnit.length} 種  ← 模型看不到單位`);
console.log('');

if (missing.length > 0) {
  console.log('='.repeat(78));
  console.log('不在對照表的指標（依 evidence 筆數排序）');
  console.log('='.repeat(78));
  for (const row of missing) {
    console.log(
      `  ${row.metricId.padEnd(38)} x${String(row.count).padEnd(5)} ` +
        `unit=${String(row.unit).padEnd(8)} elig=${String(row.youthEligibility).padEnd(13)} ` +
        `sample=${String(row.sample).slice(0, 18)}`,
    );
  }
  console.log('');
}

if (noUnit.length > 0) {
  console.log('='.repeat(78));
  console.log('unit 是 null 的指標 —— 確認每一個都是「本來就沒有單位」');
  console.log('='.repeat(78));
  console.log('（分級字串如 retentionRiskLevel、無量綱係數如 r_squared 屬於正常）');
  for (const row of noUnit) {
    console.log(
      `  ${row.metricId.padEnd(38)} x${String(row.count).padEnd(5)} ` +
        `elig=${String(row.youthEligibility).padEnd(13)} sample=${String(row.sample).slice(0, 18)}`,
    );
  }
  console.log('');
}

// 表裡有、但這份快照產不出來的 key：可能是 pipeline 改名或移除了。
const producedLeaves = new Set(all.map((row) => leafOf(row.metricId)));
const stale = [...metaKeys].filter((key) => !producedLeaves.has(key));
if (stale.length > 0) {
  console.log('='.repeat(78));
  console.log(`對照表有、但這份快照沒產出的 key（${stale.length} 個，可能已改名或移除）`);
  console.log('='.repeat(78));
  console.log(`  ${stale.join(', ')}`);
  console.log('');
}

console.log(
  `SUMMARY metrics=${all.length} missingFromMeta=${missing.length} ` +
    `noUnit=${noUnit.length} staleMetaKeys=${stale.length} evidence=${bundle.evidence.length}`,
);

// `--strict` 只看「不在對照表」，**不看 unit 是不是 null**。
// 有 18 個指標本來就沒有單位（retentionRiskLevel=low、r_squared、Shannon 指數），
// 把 noUnit 納入判斷會讓 --strict 永遠失敗，那個守門就等於沒有。
if (strict && missing.length > 0) {
  console.error(`\n--strict：有 ${missing.length} 個指標不在 ANALYTICS_METRIC_META，exit 1`);
  process.exit(1);
}
