import path from 'node:path';
import { fileURLToPath } from 'node:url';
import type { AiEvidence, AiRequestContext } from '../types/aiEvidence.js';
import { AnalyticsSnapshotEvidenceRepository } from './analyticsSnapshotRepository.js';
import { CompositeEvidenceRepository } from './compositeRepository.js';
import { CuratedFileEvidenceRepository } from './curatedFileRepository.js';
import type { EvidenceQuery, EvidenceRepository } from './evidenceRepository.js';

export * from './evidenceRepository.js';
export * from './curatedFileRepository.js';
export * from './curatedRecord.js';
export * from './analyticsSnapshot.js';
export * from './analyticsRecord.js';
export * from './analyticsSnapshotRepository.js';
export * from './compositeRepository.js';

/**
 * data-pipeline 本機輸出目錄的預設位置：`<repo>/data-pipeline/data`。
 *
 * 用 `import.meta.url` 往上推而不是 `process.cwd()`：cwd 會隨呼叫方式改變
 * （從 repo root 跑 vs 從 ai-service/ 跑 vs Lambda），而這個檔案跟 data-pipeline
 * 的相對位置是固定的。
 */
export function defaultDataPipelineDataDir(): string {
  const here = path.dirname(fileURLToPath(import.meta.url));
  // src/context → src → ai-service → <repo root>
  return path.resolve(here, '..', '..', '..', 'data-pipeline', 'data');
}

/**
 * 依環境變數決定 evidence 從哪裡來。
 *
 * 預設是 **curated ＋ analytics 兩個都讀**：
 *
 * - `CuratedFileEvidenceRepository` 給原始資料點（逐筆職缺、人口、預算與其網址）
 * - `AnalyticsSnapshotEvidenceRepository` 給彙總後的複合指標（機會指數、
 *   房價中位數、留才風險等級…）
 *
 * 兩個都預設開啟，是因為少了 analytics，AI 就沒有任何可引用的複合指標，
 * 而「哪一區的青年發展機會較好」這類核心問題**只能**用複合指標回答。
 *
 * `AI_EVIDENCE_SOURCE` 可以切換：
 * - `curated`：只讀 curated（analytics 快照還沒發布時用）
 * - `analytics`：只讀 analytics（想確認複合指標本身時用）
 * - 其他值或未設定：兩個都讀
 *
 * `AI_ANALYTICS_SNAPSHOT_ID` 可以指定讀哪個快照，省略時用 `published/current.json`。
 * `AI_DATA_DIR` 可覆寫資料目錄，測試與 Lambda 會用到。
 *
 * 架構上正式路徑仍然是 `Deterministic Analytics → DynamoDB / AI Context → AI Service`；
 * 等那張表存在時在這裡多一個 `DynamoEvidenceRepository` 分支即可，
 * handler / prompt / Bedrock 那幾層不用動（`AiEvidence` 不變）。
 */
export function createEvidenceRepositoryFromEnv(
  env: NodeJS.ProcessEnv = process.env,
): EvidenceRepository {
  const dataDir = env.AI_DATA_DIR ?? defaultDataPipelineDataDir();
  const snapshotId = env.AI_ANALYTICS_SNAPSHOT_ID;
  const mode = env.AI_EVIDENCE_SOURCE?.trim().toLowerCase();

  if (mode === 'curated') {
    return new CuratedFileEvidenceRepository(dataDir);
  }
  if (mode === 'analytics') {
    return new AnalyticsSnapshotEvidenceRepository(dataDir, snapshotId);
  }
  // curated 放前面：dedupe 與 notes 的順序都以第一個來源為主，而 curated 是
  // 原始資料，讓它先出現比較符合「先事實、後推導指標」的閱讀順序。
  return new CompositeEvidenceRepository([
    new CuratedFileEvidenceRepository(dataDir),
    new AnalyticsSnapshotEvidenceRepository(dataDir, snapshotId),
  ]);
}

export interface BuildAiContextOptions extends EvidenceQuery {
  question?: string | null;
  focusDistrict?: string | null;
  focusArea?: string | null;
  /**
   * 整個 context 最多幾筆 evidence（所有來源合併後）。預設
   * `DEFAULT_MAX_CONTEXT_EVIDENCE`。設 0 或負數代表不限制。
   */
  maxEvidence?: number;
}

/**
 * 合併後的 evidence 筆數上限。
 *
 * ⚠️ 這個上限跟延遲無關 —— `ai-service.md` 已經實測過「限制 evidence 筆數不能
 * 改善延遲」（瓶頸在輸出生成，不在 input 大小）。這裡要解決的是**不同的問題**：
 * context window 溢出。
 *
 * 實測（板橋區一區、curated ＋ 全部 7 個 analytics 分析）：
 * 1,392 筆 evidence → prompt 約 216K token，而 Claude 在 Bedrock 上是 200K window。
 * 也就是說不設上限的話，這個請求會直接被 Bedrock 拒絕，使用者拿到的是錯誤，
 * 不是「資料太多」的提示。
 *
 * `limitPerDataset` 擋不住這件事：它是**每個 dataset** 200 筆，而現在有 11 個
 * curated dataset ＋ 7 個 analytics artifact，加起來上限是 3,600 筆。
 *
 * 250 這個數字：實測平均一筆 evidence 在 prompt 裡約 420–560 字元，250 筆約
 * 12 萬字元（約 4 萬 token），留給 system prompt、few-shot 範例與模型輸出的空間充裕。
 */
export const DEFAULT_MAX_CONTEXT_EVIDENCE = 250;

/**
 * 超過上限時，每種 `metricSource` 至少保障的比例。
 *
 * ## 為什麼是配額，不是單純的優先順序
 *
 * 第一版做的是「照代表性排序，取前 N 筆」（analytics_metric → metric_id →
 * record_field）。實測直接踩雷：一個行政區的 analytics 指標有 477 筆，超過上限 250，
 * 於是 **curated 的 evidence 全部被擠掉，一筆都不剩**。
 *
 * 那個結果會打壞這個服務最重要的需求 —— 資料來源標註。逐筆的來源網址
 * （青年局預算書 PDF、職缺頁面）**只存在 curated evidence 上**，analytics 的
 * `sourceUrl` 全部是 null（彙總指標沒有單一來源頁面）。所以 curated 歸零時，
 * 回應仍然有來源機關，但失去所有可以點進去查證的連結。
 *
 * 另一個問題是 `metric_id` 那組被一起擠掉：人口數、青年局預算額這些是回答問題的
 * 基礎事實，數量很少（幾十筆），卻和 3,896 筆職缺明細被歸在同一次排序裡競爭。
 *
 * ## 配額怎麼分
 *
 * 每一組先拿到保障配額，用不完的還回去給其他組（照代表性順序），所以不會浪費額度。
 * 比例的理由：
 * - `analytics_metric` 50%：彙總指標是回答「哪一區比較好」唯一能引用的東西，
 *   而且一筆一個面向，資訊密度最高。
 * - `metric_id` 30%：基礎事實，總量本來就少，30% 幾乎一定用不完（會還回去）。
 * - `record_field` 20%：單筆記錄，guardrails 規則 7 明講「單筆不代表全區水準」，
 *   所以留最少 —— 但不能是 0，因為逐筆網址在這裡。
 */
const METRIC_SOURCE_QUOTA: readonly { metricSource: string; share: number }[] = [
  { metricSource: 'analytics_metric', share: 0.5 },
  { metricSource: 'metric_id', share: 0.3 },
  { metricSource: 'record_field', share: 0.2 },
];

export function prioritizeEvidenceForContext(
  evidence: readonly AiEvidence[],
  maxEvidence: number,
): { evidence: AiEvidence[]; dropped: number; droppedBySource: Record<string, number> } {
  if (maxEvidence <= 0 || evidence.length <= maxEvidence) {
    return { evidence: [...evidence], dropped: 0, droppedBySource: {} };
  }

  // 依 metricSource 分組，組內維持原本的來源順序（curated 先、analytics 後），
  // 這樣同樣的輸入一定得到同樣的輸出。
  const groups = new Map<string, { item: AiEvidence; index: number }[]>();
  evidence.forEach((item, index) => {
    const bucket = groups.get(item.metricSource);
    if (bucket) {
      bucket.push({ item, index });
    } else {
      groups.set(item.metricSource, [{ item, index }]);
    }
  });

  // 第一輪：各組拿保障配額。
  const allocation = new Map<string, number>();
  let remaining = maxEvidence;
  for (const { metricSource, share } of METRIC_SOURCE_QUOTA) {
    const available = groups.get(metricSource)?.length ?? 0;
    const take = Math.min(available, Math.floor(maxEvidence * share));
    allocation.set(metricSource, take);
    remaining -= take;
  }
  // 沒被列在配額表裡的 metricSource（未來新增時）也要拿得到額度，不能靜默消失。
  for (const metricSource of groups.keys()) {
    if (!allocation.has(metricSource)) {
      allocation.set(metricSource, 0);
    }
  }

  // 第二輪：把用不完的額度照代表性順序還回去。
  const order = [
    ...METRIC_SOURCE_QUOTA.map((quota) => quota.metricSource),
    ...[...groups.keys()].filter(
      (source) => !METRIC_SOURCE_QUOTA.some((quota) => quota.metricSource === source),
    ),
  ];
  for (const metricSource of order) {
    if (remaining <= 0) {
      break;
    }
    const available = groups.get(metricSource)?.length ?? 0;
    const current = allocation.get(metricSource) ?? 0;
    const extra = Math.min(remaining, available - current);
    if (extra > 0) {
      allocation.set(metricSource, current + extra);
      remaining -= extra;
    }
  }

  const kept: { item: AiEvidence; index: number }[] = [];
  const droppedBySource: Record<string, number> = {};
  for (const [metricSource, items] of groups) {
    const take = allocation.get(metricSource) ?? 0;
    kept.push(...items.slice(0, take));
    if (items.length > take) {
      droppedBySource[metricSource] = items.length - take;
    }
  }

  // 還原成原本的來源順序，讓 prompt 的閱讀順序保持穩定可預期。
  kept.sort((left, right) => left.index - right.index);
  return {
    evidence: kept.map(({ item }) => item),
    dropped: evidence.length - kept.length,
    droppedBySource,
  };
}

/**
 * 從 evidence 來源組出一個可以直接餵給 handler 的請求。
 *
 * 回傳的是 `AiRequestContext`（evidence 允許為空），而不是 `AiContext`：
 * 「這一區這個主題沒有資料」是正常結果，應該讓 handler 走「資料不足」路徑誠實回答，
 * 不該在這裡就丟錯。
 *
 * repository 回報的 `notes`（截斷、缺少 dataset、品質旗標…）會原封不動放進
 * `knownLimitations`，最後一定會出現在輸出的 limitations 裡（見 `runFeature`）。
 */
export async function buildAiContext(
  repository: EvidenceRepository,
  options: BuildAiContextOptions = {},
): Promise<AiRequestContext> {
  const { question, focusDistrict, focusArea, maxEvidence, ...rest } = options;

  // focusArea 要傳給 repository，不能在這裡被丟掉：analytics repository 用它決定
  // 要讀哪幾個分析（見 ANALYTICS_ARTIFACTS_BY_FOCUS_AREA）。少了它，一個行政區
  // 的請求會把 7 個分析全讀進來（實測 477 筆 evidence）。
  const query: EvidenceQuery = { ...rest, focusArea: focusArea ?? null };

  // 使用者選了行政區時，把它當成預設的篩選條件，否則會把 29 區的資料全撈進來。
  const effectiveQuery: EvidenceQuery =
    query.districtNames === undefined && query.districtIds === undefined && focusDistrict
      ? { ...query, districtNames: [focusDistrict] }
      : query;

  const bundle = await repository.query(effectiveQuery);
  const limit = maxEvidence ?? DEFAULT_MAX_CONTEXT_EVIDENCE;
  const prioritized = prioritizeEvidenceForContext(bundle.evidence, limit);

  return {
    question: question ?? null,
    focusDistrict: focusDistrict ?? null,
    focusArea: focusArea ?? null,
    evidence: prioritized.evidence,
    // 上網搜尋預設關閉：犧牲可追溯性的行為必須由使用者明確開啟。
    webFindings: [],
    webSearch: { enabled: false, contextSize: 'low' },
    knownLimitations: [
      ...bundle.notes,
      // 截斷一定要說。不說的話模型會拿 250 筆當成全部資料去解讀，
      // 那正是 ai-service.md 禁止的「假裝資料充足」。
      ...(prioritized.dropped > 0
        ? [
            `本次符合條件的 evidence 共 ${bundle.evidence.length} 筆，超過單次 context 上限 ${limit} 筆，` +
              `已省略 ${prioritized.dropped} 筆（${describeDropped(prioritized.droppedBySource)}）。` +
              '省略的優先順序是「單筆記錄值」先於「彙總指標」，因為單筆不代表全區水準；' +
              '但這仍表示本次看到的不是全部資料，不可據此推論全體分布。',
          ]
        : []),
      ...(prioritized.evidence.length === 0
        ? [`evidence 來源 ${repository.description} 在本次條件下沒有回傳任何資料點。`]
        : []),
    ],
  };
}

function describeDropped(droppedBySource: Readonly<Record<string, number>>): string {
  const labels: Readonly<Record<string, string>> = {
    analytics_metric: '彙總指標',
    metric_id: '資料集指標',
    record_field: '單筆記錄值',
  };
  return Object.entries(droppedBySource)
    .map(([source, count]) => `${labels[source] ?? source} ${count} 筆`)
    .join('、');
}
