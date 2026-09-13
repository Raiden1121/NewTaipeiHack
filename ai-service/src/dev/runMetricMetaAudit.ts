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
  COMPARISON_METRIC_RULES,
  defaultDataPipelineDataDir,
  readAnalyticsSnapshot,
} from '../context/buildContext.js';
import type { AiEvidence } from '../types/aiEvidence.js';
import { SOURCE_CONFIG_SNAPSHOT } from '../context/generated/analyticsConfig.js';
import { readAnalyticsConfig } from './syncAnalyticsConfig.js';

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

// ---------------------------------------------------------------------------
// 跨區比較的覆蓋率
//
// 「為什麼 X 排第幾／這麼高」這類問題，只有當那個指標在某條規則的 `metricIds`
// 裡（也就是會跨 29 區取）時才答得出來。只在 `focusMetricIds` 的話模型只拿到
// 焦點行政區自己的數字，就會回「無法確認排名」—— 實測踩過兩次。
//
// 比對用**實際 evidence 的 metricId**（帶路徑，例如
// `service_coverage.covered_youth`），不是葉名，否則會誤判。
// ---------------------------------------------------------------------------
const districtsOf = new Map<string, Set<string>>();
for (const item of bundle.evidence) {
  if (item.districtName === null) {
    continue;
  }
  const base = item.metricId.split('#')[0]!;
  const set = districtsOf.get(base) ?? new Set<string>();
  set.add(item.districtName);
  districtsOf.set(base, set);
}
const districtCount = new Set(
  bundle.evidence.map((item) => item.districtName).filter((name) => name !== null),
).size;

// 至少 8 成行政區都有值 = 這個指標可以拿來排名。
const RANKABLE_THRESHOLD = 0.8;
const rankable = [...districtsOf.entries()]
  .filter(([, set]) => districtCount > 0 && set.size >= districtCount * RANKABLE_THRESHOLD)
  .map(([metricId]) => metricId)
  .sort();

const comparisonIds = new Set(COMPARISON_METRIC_RULES.flatMap((rule) => [...rule.metricIds]));
const focusOnlyIds = new Set(COMPARISON_METRIC_RULES.flatMap((rule) => [...rule.focusMetricIds]));
const reachable = (metricId: string): boolean =>
  comparisonIds.has(metricId) || comparisonIds.has(metricId.split('.').pop() ?? metricId);
const inFocus = (metricId: string): boolean =>
  focusOnlyIds.has(metricId) || focusOnlyIds.has(metricId.split('.').pop() ?? metricId);

const notComparable = rankable.filter((metricId) => !reachable(metricId));
const focusOnly = notComparable.filter((metricId) => inFocus(metricId));
const uncovered = notComparable.filter((metricId) => !inFocus(metricId));

console.log('='.repeat(78));
console.log(`跨區比較覆蓋率（${districtCount} 區，門檻 ${RANKABLE_THRESHOLD * 100}%）`);
console.log('='.repeat(78));
console.log(`可排名的指標    : ${rankable.length}`);
console.log(`跨區拿得到      : ${rankable.length - notComparable.length}`);
console.log(`⚠️ 只在 focus    : ${focusOnly.length}（問排名會答「無法確認」）`);
console.log(`❌ 兩個表都沒有 : ${uncovered.length}`);
if (focusOnly.length > 0) {
  console.log('');
  for (const metricId of focusOnly) {
    console.log(`  focus-only  ${metricId}`);
  }
}
if (uncovered.length > 0) {
  console.log('');
  for (const metricId of uncovered) {
    console.log(`  uncovered   ${metricId}`);
  }
}
console.log('');

// ---------------------------------------------------------------------------
// 產生出來的 analytics config 有沒有跟 pipeline 的來源漂移
//
// `src/context/generated/analyticsConfig.ts` 是 pipeline config 的投影，
// 而 prompt 上的權重（「就業子分數 × 0.25」）直接來自它。pipeline 改了權重卻
// 沒有人重跑 `npm run sync:metric-config` 的話，模型會拿**舊權重**去算貢獻度，
// 算出來的數字有理有據但是錯的 —— 那比沒有權重更糟。
// ---------------------------------------------------------------------------
let configDrift = 0;
try {
  const live = await readAnalyticsConfig();
  const projected = SOURCE_CONFIG_SNAPSHOT as unknown as Record<string, unknown>;
  const liveSubset = {
    version: live.version,
    normalization: live.normalization,
    yoi_weights: live.yoi_weights,
    fafi: live.fafi,
    service_radius_m: live.service_radius_m,
  };
  const liveJson = JSON.stringify(liveSubset);
  const projectedJson = JSON.stringify({
    version: projected.version,
    normalization: projected.normalization,
    yoi_weights: projected.yoi_weights,
    fafi: projected.fafi,
    service_radius_m: projected.service_radius_m,
  });

  console.log('='.repeat(78));
  console.log('analytics config 投影');
  console.log('='.repeat(78));
  if (liveJson === projectedJson) {
    console.log(`一致（v${live.version}）：generated/analyticsConfig.ts 跟 pipeline config 相同`);
  } else {
    configDrift = 1;
    console.error('❌ 漂移：generated/analyticsConfig.ts 跟 pipeline config 不一致');
    console.error(`  pipeline : ${liveJson}`);
    console.error(`  generated: ${projectedJson}`);
    console.error('  修法：npm run sync:metric-config，然後 commit 產生出來的檔案。');
  }
  console.log('');
} catch (error) {
  console.error(`讀不到 pipeline config，跳過漂移偵測：${error instanceof Error ? error.message : String(error)}`);
  console.log('');
}

console.log(
  `SUMMARY metrics=${all.length} missingFromMeta=${missing.length} ` +
    `noUnit=${noUnit.length} staleMetaKeys=${stale.length} evidence=${bundle.evidence.length} ` +
    `rankable=${rankable.length} focusOnly=${focusOnly.length} uncovered=${uncovered.length} ` +
    `configDrift=${configDrift}`,
);

// `--strict` 只看「不在對照表」，**不看 unit 是不是 null**。
// 有 18 個指標本來就沒有單位（retentionRiskLevel=low、r_squared、Shannon 指數），
// 把 noUnit 納入判斷會讓 --strict 永遠失敗，那個守門就等於沒有。
if (strict && (missing.length > 0 || configDrift > 0)) {
  console.error(
    `\n--strict：missingFromMeta=${missing.length} configDrift=${configDrift}，exit 1`,
  );
  process.exit(1);
}
