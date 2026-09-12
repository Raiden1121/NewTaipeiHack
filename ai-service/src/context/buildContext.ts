import path from 'node:path';
import { fileURLToPath } from 'node:url';
import type { AiEvidence, AiRequestContext } from '../types/aiEvidence.js';
import type { WebSearchScope, WebSearchSettings } from '../types/webFinding.js';
import { AnalyticsSnapshotEvidenceRepository } from './analyticsSnapshotRepository.js';
import { CompositeEvidenceRepository } from './compositeRepository.js';
import { CuratedFileEvidenceRepository } from './curatedFileRepository.js';
import {
  DEFAULT_LIMIT_PER_DATASET,
  type EvidenceQuery,
  type EvidenceRepository,
} from './evidenceRepository.js';
import { inferComparisonMetrics, inferFocusMetrics } from './comparisonMetrics.js';

export * from './evidenceRepository.js';
export * from './curatedFileRepository.js';
export * from './curatedRecord.js';
export * from './analyticsSnapshot.js';
export * from './analyticsRecord.js';
export * from './analyticsSnapshotRepository.js';
export * from './compositeRepository.js';
export * from './comparisonMetrics.js';

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
  /**
   * 上網搜尋設定。**預設開啟**（`enabled: true`、`contextSize: 'low'`）。
   * 只想覆寫其中一項時可以只傳那一項。
   */
  webSearch?: Partial<WebSearchSettings>;
  /**
   * 這些 metricId **不受行政區篩選限制**，會額外撈全 29 區的值進 context。
   *
   * 用途是跨區比較與排名問題。`focusDistrict` 的預設篩選會把 evidence 縮成一區，
   * 那對「為何八里薪資第六高」這種問題是致命的 —— 模型看得到八里的數字，
   * 卻無法知道它排第幾，只能照抄使用者的前提（而前提可能是錯的）。
   *
   * Q&A 會用 `inferComparisonMetrics(question)` 自動推導，見 `comparisonMetrics.ts`。
   * Dashboard 的 explain / policy 不需要（它們沒有使用者問題）。
   */
  comparisonMetrics?: readonly string[];
  /**
   * 焦點行政區這次只取這些 metricId。**傳 `[]` 代表不限制。**
   *
   * 省略時由 `inferFocusMetrics(question)` 從問題推導（主題對不上就不限制）。
   * 目的是降低 input token —— 實測同一個問題 6 筆 vs 250 筆 evidence 差 7.8 秒。
   *
   * 呼叫端自己傳了 `metricIds` 時這個不生效（明確指定優先）。
   */
  focusMetricIds?: readonly string[];
}

/**
 * 指標收斂生效時，每個 dataset 的取樣上限。
 *
 * 比預設的 200 小很多。理由：收斂之後彙總指標都在了，curated 逐筆記錄的作用是
 * 讓模型判斷「母體多大、資料品質有沒有問題」—— 30 筆就足以看出
 * `query_district_mismatch_filtered` 這類旗標與薪資的分布形狀，
 * 200 筆只是多付 token（而 input 每 1K token 約 0.2 秒）。
 */
export const FOCUSED_LIMIT_PER_DATASET = 30;

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
  const {
    question,
    focusDistrict,
    focusArea,
    maxEvidence,
    webSearch,
    comparisonMetrics,
    focusMetricIds,
    ...rest
  } = options;

  // focusArea 要傳給 repository，不能在這裡被丟掉：analytics repository 用它決定
  // 要讀哪幾個分析（見 ANALYTICS_ARTIFACTS_BY_FOCUS_AREA）。少了它，一個行政區
  // 的請求會把 7 個分析全讀進來（實測 477 筆 evidence）。
  const query: EvidenceQuery = { ...rest, focusArea: focusArea ?? null };

  // 使用者選了行政區時，把它當成預設的篩選條件，否則會把 29 區的資料全撈進來。
  const districtScopedQuery: EvidenceQuery =
    query.districtNames === undefined && query.districtIds === undefined && focusDistrict
      ? { ...query, districtNames: [focusDistrict] }
      : query;

  // 依問題主題收斂焦點行政區的指標。
  //
  // 為什麼：input 是真的有成本（實測同一個問題 6 筆 vs 250 筆差 7.8 秒），而
  // 「為何八里薪資高」不需要生育率、服務涵蓋率、議題關鍵詞 —— 焦點行政區的
  // analytics 有 121 筆，其中大多數跟問題無關。
  //
  // 只在「呼叫端沒有自己指定 metricIds」且「主題判斷成功」時才套用。
  // 主題對不上就維持原本什麼都給的行為（見 `inferFocusMetrics`）。
  const focusMetrics = focusMetricIds ?? inferFocusMetrics(question);
  const applyFocusScope = query.metricIds === undefined && focusMetrics.length > 0;
  const effectiveQuery: EvidenceQuery = applyFocusScope
    ? {
        ...districtScopedQuery,
        metricIds: focusMetrics,
        // 指標收斂之後，每個 dataset 仍然可能有大量逐筆記錄符合條件
        // （例如 200 筆職缺各有 salary_lower）。彙總指標已經在了，逐筆的作用是
        // 讓模型判斷母體與資料品質，30 筆足夠 —— 200 筆只是多付 token。
        limitPerDataset: Math.min(
          districtScopedQuery.limitPerDataset ?? DEFAULT_LIMIT_PER_DATASET,
          FOCUSED_LIMIT_PER_DATASET,
        ),
      }
    : districtScopedQuery;

  const bundle = await repository.query(effectiveQuery);

  // 跨區比較資料。跟主查詢分開跑，因為它要的正好是主查詢排除掉的東西：
  // 其他 28 區的同一個指標。
  //
  // 沒有明確指定時，從使用者問題自動推導。這樣 backend 不需要知道這件事的存在，
  // 而 explain / policy 因為 question 是 null，自然不會受影響。
  // 要明確關掉就傳 `comparisonMetrics: []`。
  //
  // 呼叫端自己傳了 `metricIds` 時也不推導：那代表它要完全接管取用範圍，
  // 這時候還自動加幾個它沒要求的跨區指標會很難預期。需要的話明確傳
  // `comparisonMetrics` 就好。
  const effectiveComparisonMetrics =
    comparisonMetrics ?? (query.metricIds === undefined ? inferComparisonMetrics(question) : []);
  const comparison = await queryComparisonEvidence(repository, query, effectiveComparisonMetrics);

  // 比較資料刻意放**最前面**。
  //
  // `prioritizeEvidenceForContext()` 超過上限時是「每組取前 N 筆」，所以順序就是
  // 優先權。跨區比較的值是這類問題的核心證據 —— 排在焦點區的 121 筆之後的話，
  // 配額用完就被截掉了，於是「答不出排名」的問題又回來了。
  const mergedEvidence = dedupeByEvidenceId([...comparison.evidence, ...bundle.evidence]);

  const limit = maxEvidence ?? DEFAULT_MAX_CONTEXT_EVIDENCE;
  const prioritized = prioritizeEvidenceForContext(mergedEvidence, limit);

  return {
    question: question ?? null,
    focusDistrict: focusDistrict ?? null,
    focusArea: focusArea ?? null,
    evidence: prioritized.evidence,
    webFindings: [],
    /**
     * 上網搜尋**預設開啟**。
     *
     * 原本預設是關閉的，理由是「犧牲可追溯性的行為必須由使用者明確開啟」。
     * 那個顧慮沒有消失，但它已經由別的機制處理掉了，而不是靠「預設不要用」：
     *
     * - `webReferences` 與 `basis` 是**分開的陣列**，前端分得出「有官方統計支撐」
     *   和「某個網頁說的」
     * - 引用網路來源時，`limitations` 一定會有一條說明，而且
     *   `dataSufficiency` 不可能是 `sufficient`
     * - `findUnknownFindingIds()` 擋掉模型憑記憶編網址
     *
     * 而開啟的理由是這個服務的定位：Q&A 要做的是**數據解釋**。
     * 「為何八里薪資排在前面」這種問題，資料管線能給的是「相關的指標長什麼樣」，
     * 給不出「八里有台北港與工業區」這種地理與產業背景 —— 那個背景只能上網拿。
     * 預設關閉等於預設放棄解釋能力。
     *
     * 仍然可以關：呼叫端傳 `webSearch: { enabled: false }`，
     * 或在伺服器端設 `WEB_SEARCH_PROVIDER=off`（那個優先，見 factory）。
     */
    webSearch: {
      enabled: webSearch?.enabled ?? true,
      contextSize: webSearch?.contextSize ?? 'low',
      // `all`（全網）或 `trusted`（只搜 gov.tw / edu.tw）。
      // 這是使用者的選擇，所以優先吃傳進來的值；沒傳就用伺服器端的預設。
      scope: webSearch?.scope ?? defaultWebSearchScope(),
    },
    knownLimitations: [
      ...bundle.notes,
      ...comparison.notes,
      // 指標收斂一定要說。不說的話模型會以為手上就是全部資料，
      // 而使用者也無從知道「我問的面向被縮小了」。
      ...(applyFocusScope
        ? [
            `本次依問題主題收斂了取用範圍：${focusDistrict ?? '焦點行政區'}只取與問題相關的指標` +
              `（${focusMetrics.length} 個指標，每個資料集最多 ${FOCUSED_LIMIT_PER_DATASET} 筆）。` +
              '其他面向的指標本次未納入，若問題涉及那些面向，本次回應無法涵蓋。',
          ]
        : []),
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

/**
 * 伺服器端的搜尋範圍預設值。
 *
 * `WEB_SEARCH_SCOPE=trusted` 可以把整個服務的預設改成只搜可信來源。
 * 前端那顆開關（`webSearch.scope`）仍然可以逐請求覆寫 —— 這裡只是預設。
 *
 * 要「使用者不能選全網」的話，設 `WEB_SEARCH_INCLUDE_DOMAINS`，
 * 那是 provider 層的硬限制，會跟使用者的選擇取交集。
 */
function defaultWebSearchScope(env: NodeJS.ProcessEnv = process.env): WebSearchScope {
  return env.WEB_SEARCH_SCOPE?.trim().toLowerCase() === 'trusted' ? 'trusted' : 'all';
}

/**
 * 撈跨區比較用的 evidence。
 *
 * 刻意**不帶**行政區篩選，也不帶 `metricIds` 以外的既有條件裡跟區域相關的部分 ——
 * 這個查詢要的就是全 29 區的同一個指標。
 *
 * 回傳的 notes 會告訴模型「這些指標有全區資料可以比較」。這句話不是裝飾：
 * 沒有它的話，模型看到 29 筆同名指標可能以為是重複資料，或者不確定手上是否
 * 真的涵蓋所有行政區，於是不敢下排名的判斷。
 */
async function queryComparisonEvidence(
  repository: EvidenceRepository,
  baseQuery: EvidenceQuery,
  comparisonMetrics: readonly string[] | undefined,
): Promise<{ evidence: AiEvidence[]; notes: string[] }> {
  if (comparisonMetrics === undefined || comparisonMetrics.length === 0) {
    return { evidence: [], notes: [] };
  }

  const { districtNames: _names, districtIds: _ids, metricIds: _metrics, ...withoutScope } = baseQuery;
  const bundle = await repository.query({
    ...withoutScope,
    metricIds: [...comparisonMetrics],
    // 29 區 × 幾個指標，200 的預設上限夠用；明確寫出來免得被別處的預設影響。
    limitPerDataset: 400,
  });

  if (bundle.evidence.length === 0) {
    return {
      evidence: [],
      notes: [
        `本次嘗試取得跨行政區的比較資料（${comparisonMetrics.join('、')}）但沒有結果，` +
          '因此無法回答排名或跨區比較類的問題。',
      ],
    };
  }

  const districts = new Set(
    bundle.evidence
      .map((item) => item.districtName)
      .filter((name): name is string => typeof name === 'string'),
  );

  return {
    evidence: bundle.evidence,
    notes: [
      `本次額外納入跨行政區的比較資料：${comparisonMetrics.join('、')}，` +
        `涵蓋 ${districts.size} 個行政區。排名與跨區比較只能依據這些指標，` +
        '其他指標本次只有焦點行政區的值。',
    ],
  };
}

/**
 * 依 evidenceId 去重。
 *
 * 需要它是因為跨區查詢一定會把焦點行政區自己那一筆再撈一次 ——
 * 同一個 evidenceId 出現兩次會讓模型以為有兩個獨立來源，
 * 那正是 `dedupeAnalyticsEvidence()` 在防的同一類問題。
 */
function dedupeByEvidenceId(evidence: readonly AiEvidence[]): AiEvidence[] {
  const seen = new Set<string>();
  const kept: AiEvidence[] = [];
  for (const item of evidence) {
    if (seen.has(item.evidenceId)) {
      continue;
    }
    seen.add(item.evidenceId);
    kept.push(item);
  }
  return kept;
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
