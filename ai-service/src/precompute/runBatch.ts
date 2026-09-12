/**
 * 批次產生 explain / policyCopilot 的預先算結果：`npm run precompute`
 *
 * ## 為什麼要有這支
 *
 * explain 與 policyCopilot 沒有使用者問題，輸出是
 * `(行政區, 主題, 那批 evidence)` 的純函數，而且是給 dashboard 卡片用的。
 * 實測 Sonnet 4-6 各要 50 秒與 58 秒，遠超 API Gateway HTTP API 固定的 30 秒
 * 上限。即時算不可能成功，所以離線算好、線上讀現成的。
 *
 * ## 用法
 *
 *   npm run precompute -- --dry                          # 只看要跑幾組、估多久
 *   npm run precompute -- --districts=板橋區,八里區        # 指定行政區
 *   npm run precompute -- --all --areas=employment       # 29 區的 employment
 *   npm run precompute -- --all --concurrency=3
 *
 * 沒有 `--districts` 也沒有 `--all` 會直接停下來並印出用法 —— 這支腳本每一組
 * 要花 50 秒以上並產生 Bedrock 費用，不該有「不小心跑了全部」這種預設行為。
 *
 * 輸出位置由 `AI_PRECOMPUTE_DIR` 決定，沒設就停下來（不猜一個位置寫檔）。
 */
import { createBedrockClientFromEnv, MockBedrockClient, type BedrockClient } from '../bedrock/client.js';
import {
  buildAiContext,
  createEvidenceRepositoryFromEnv,
  defaultDataPipelineDataDir,
  readAnalyticsSnapshot,
} from '../context/buildContext.js';
import { ANALYTICS_ARTIFACTS_BY_FOCUS_AREA } from '../context/analyticsSnapshotRepository.js';
import { explainData } from '../handlers/explainData.js';
import { policyCopilot } from '../handlers/policyCopilot.js';
import { createWebSearchProviderFromEnv } from '../websearch/factory.js';
import type { AiFeatureResult } from '../handlers/runFeature.js';
import { contextFingerprint } from './fingerprint.js';
import { buildEntry, PRECOMPUTABLE_ACTIONS, type PrecomputableAction } from './servePrecomputed.js';
import { createPrecomputedStoreFromEnv, DisabledPrecomputedStore } from './store.js';
import { defaultDistrictsFile, readDistrictNames } from './districts.js';

/** 每組的平均耗時，只用來在開跑前估總時間。實測 explain 50s、policy 58s。 */
const ESTIMATED_MS_PER_JOB = 55_000;

const args = process.argv.slice(2);
const flags = new Set(args.filter((arg) => arg.startsWith('--') && !arg.includes('=')));
const options = new Map(
  args
    .filter((arg) => arg.startsWith('--') && arg.includes('='))
    .map((arg) => {
      const [key, ...rest] = arg.slice(2).split('=');
      return [key, rest.join('=')] as const;
    }),
);

const dryRun = flags.has('--dry');
const dataDir = process.env.AI_DATA_DIR ?? defaultDataPipelineDataDir();

const store = createPrecomputedStoreFromEnv();
if (store instanceof DisabledPrecomputedStore && !dryRun) {
  console.error(
    '沒有設 AI_PRECOMPUTE_DIR，不知道要把結果寫到哪裡。\n' +
      '例如：$env:AI_PRECOMPUTE_DIR="../data-pipeline/data/ai-precomputed"',
  );
  process.exit(1);
}

const areas = parseList(options.get('areas')) ?? ['employment'];
const unknownAreas = areas.filter((area) => ANALYTICS_ARTIFACTS_BY_FOCUS_AREA[area] === undefined);
if (unknownAreas.length > 0) {
  console.error(
    `主題 ${unknownAreas.join('、')} 沒有對應的 analytics 範圍設定。\n` +
      `合法值：${Object.keys(ANALYTICS_ARTIFACTS_BY_FOCUS_AREA).join(' / ')}`,
  );
  process.exit(1);
}

const actions = (parseList(options.get('actions')) ?? [...PRECOMPUTABLE_ACTIONS]) as PrecomputableAction[];
const unknownActions = actions.filter(
  (action) => !(PRECOMPUTABLE_ACTIONS as readonly string[]).includes(action),
);
if (unknownActions.length > 0) {
  console.error(
    `action ${unknownActions.join('、')} 不能預先算。合法值：${PRECOMPUTABLE_ACTIONS.join(' / ')}。\n` +
      'Q&A 不在裡面：它的輸出取決於使用者當下打的問題，預先算不可能涵蓋。',
  );
  process.exit(1);
}

const explicitDistricts = parseList(options.get('districts'));
if (explicitDistricts === undefined && !flags.has('--all')) {
  console.error(
    '要指定 --districts=板橋區,八里區 或 --all。\n' +
      '不給預設值是刻意的：每一組要 50 秒以上並產生 Bedrock 費用，' +
      '不該有「不小心跑了全部 29 區」這種預設行為。\n' +
      '先用 --dry 看要跑幾組、估多久。',
  );
  process.exit(1);
}

const districts =
  explicitDistricts ?? (await readDistrictNames(defaultDistrictsFile(dataDir)));

const concurrency = Math.max(1, Number.parseInt(options.get('concurrency') ?? '2', 10) || 2);

const snapshot = await readAnalyticsSnapshot(dataDir, process.env.AI_ANALYTICS_SNAPSHOT_ID);

interface Job {
  action: PrecomputableAction;
  district: string;
  area: string;
}

const jobs: Job[] = [];
for (const district of districts) {
  for (const area of areas) {
    for (const action of actions) {
      jobs.push({ action, district, area });
    }
  }
}

console.log(`快照        : ${snapshot.snapshotId}`);
console.log(`輸出位置    : ${store.description}`);
console.log(`行政區      : ${districts.length} 區（${districts.slice(0, 5).join('、')}${districts.length > 5 ? '…' : ''}）`);
console.log(`主題        : ${areas.join('、')}`);
console.log(`action      : ${actions.join('、')}`);
console.log(`共          : ${jobs.length} 組，併發 ${concurrency}`);
console.log(
  `粗估        : ${Math.ceil((jobs.length * ESTIMATED_MS_PER_JOB) / concurrency / 60_000)} 分鐘` +
    `（每組約 ${Math.round(ESTIMATED_MS_PER_JOB / 1000)} 秒）`,
);
console.log('');

if (dryRun) {
  console.log('--dry：不呼叫模型，結束。');
  process.exit(0);
}

const client: BedrockClient = createBedrockClientFromEnv();
if (client instanceof MockBedrockClient) {
  console.error('預先算的結果會被線上直接回給使用者，用 Mock 產生沒有意義。請先設定好 .env。');
  process.exit(1);
}
const searchProvider = createWebSearchProviderFromEnv();
console.log(`模型        : ${client.description}`);
console.log(`搜尋        : ${searchProvider.description}`);
console.log('');

// **一定要跟線上用同一個來源決定。** 快取鍵是輸入內容的指紋，來源不一樣 →
// evidence 不一樣 → 指紋不一樣 → 線上每次都 miss，等於這整批白跑。
// 所以這裡走 createEvidenceRepositoryFromEnv()（預設只讀 analytics），
// 不自己組 Composite。
const repository = createEvidenceRepositoryFromEnv();

interface JobResult {
  job: Job;
  ok: boolean;
  elapsedMs: number;
  message: string;
}

const results: JobResult[] = [];
let nextIndex = 0;
const startedAll = Date.now();

/**
 * 併發用「共用游標」而不是把 jobs 切成 N 等份：每組耗時差很多
 * （explain 比 policyCopilot 快 8 秒以上），切等份會讓最慢的那份拖住整批。
 */
async function worker(): Promise<void> {
  for (;;) {
    const index = nextIndex;
    nextIndex += 1;
    if (index >= jobs.length) {
      return;
    }
    const job = jobs[index]!;
    const label = `${job.action} ${job.district} ${job.area}`;
    const startedAt = Date.now();
    try {
      const context = await buildAiContext(repository, {
        focusDistrict: job.district,
        focusArea: job.area,
      });
      if (context.evidence.length === 0) {
        results.push({
          job,
          ok: false,
          elapsedMs: Date.now() - startedAt,
          message: '沒有任何 evidence，跳過（不寫入空結果）',
        });
        console.log(`[${index + 1}/${jobs.length}] SKIP ${label} —— 沒有 evidence`);
        continue;
      }

      const result = await run(job.action, context);
      const elapsedMs = Date.now() - startedAt;
      await store.put(
        buildEntry({
          fingerprint: contextFingerprint(job.action, context),
          action: job.action,
          context,
          client,
          result,
          elapsedMs,
          snapshotId: snapshot.snapshotId,
        }),
      );
      results.push({ job, ok: true, elapsedMs, message: 'ok' });
      console.log(
        `[${index + 1}/${jobs.length}] OK   ${label}  ${elapsedMs} ms  ` +
          `basis=${result.output.basis.length} sufficiency=${result.output.dataSufficiency}`,
      );
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      results.push({ job, ok: false, elapsedMs: Date.now() - startedAt, message });
      // 一組失敗不該中斷整批：跑了 20 分鐘因為最後一區壞掉而全部重來是最糟的結果。
      console.log(`[${index + 1}/${jobs.length}] FAIL ${label} —— ${message}`);
    }
  }
}

async function run(action: PrecomputableAction, context: Parameters<typeof explainData>[1]): Promise<AiFeatureResult> {
  if (action === 'explain') {
    return explainData(client, context, searchProvider);
  }
  return policyCopilot(client, context, searchProvider);
}

function parseList(value: string | undefined): string[] | undefined {
  if (value === undefined) {
    return undefined;
  }
  const items = value
    .split(',')
    .map((item) => item.trim())
    .filter((item) => item.length > 0);
  return items.length > 0 ? items : undefined;
}

await Promise.all(Array.from({ length: Math.min(concurrency, jobs.length) }, () => worker()));

const totalMs = Date.now() - startedAll;
const ok = results.filter((item) => item.ok);
const failed = results.filter((item) => !item.ok);

console.log('');
console.log('='.repeat(78));
console.log(`SUMMARY total=${jobs.length} ok=${ok.length} failed=${failed.length} totalMs=${totalMs}`);
if (ok.length > 0) {
  const times = ok.map((item) => item.elapsedMs).sort((left, right) => left - right);
  console.log(
    `SUMMARY perJobMs min=${times[0]} median=${times[Math.floor(times.length / 2)]} max=${times[times.length - 1]}`,
  );
}
for (const item of failed) {
  console.log(`FAILED ${item.job.action} ${item.job.district} ${item.job.area} —— ${item.message}`);
}
if (failed.length > 0) {
  process.exit(1);
}
