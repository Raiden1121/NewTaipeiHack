import { z } from 'zod';
import type { AiEvidence } from './aiEvidence.js';
import type { StructuredOutput } from './structuredOutput.js';
import type { WebFinding } from './webFinding.js';

/**
 * 資料來源標註。
 *
 * **這個清單是程式從 evidence 算出來的，不是模型產生的。** 這是刻意的設計：
 * 網址與機關名稱是最容易被 LLM 編得像真的東西（一個看起來合理但不存在的
 * data.gov.tw 連結，人是看不出來的）。所以模型只負責寫分析，來源一律由程式
 * 從實際被引用的 evidence 推導，這樣就不可能出現捏造的來源。
 */
export const SourceAttributionSchema = z.object({
  /** curated record 的 `source` 值，例如 `moi_household_registration` */
  sourceId: z.string(),
  /** 中文的資料提供機關 */
  organization: z.string().nullable(),
  /** 中文的資料集名稱 */
  datasetLabel: z.string().nullable(),
  kind: z.enum(['dataset', 'document', 'web']),
  /** 資料集層級的官方頁面（來自 SOURCE_REGISTRY） */
  url: z.string().nullable(),
  /** 逐筆層級的網址（例如某份預算書 PDF、某個職缺頁面），最多列幾筆 */
  recordUrls: z.array(z.string()),
  /** 用到這個來源的 canonical dataset 名稱 */
  datasets: z.array(z.string()),
  /** 實際被 basis 引用的 evidenceId */
  citedEvidenceIds: z.array(z.string()),
  /** 本地檔案路徑或 DB 參照，用來回溯這份 evidence 是從哪個檔案／欄位來的 */
  sourcePaths: z.array(z.string()),
  /** 這批 evidence 裡最新的抓取時間，讓使用者知道資料多舊 */
  fetchedAt: z.string().nullable(),
});
export type SourceAttribution = z.infer<typeof SourceAttributionSchema>;

interface SourceRegistryEntry {
  organization: string;
  datasetLabel: string;
  kind: 'dataset' | 'document' | 'web';
  url: string | null;
}

/**
 * `source` 值 → 中文機關與官方頁面。
 *
 * 這 8 個是實測 `data-pipeline` 產出的 11 個 dataset 後得到的完整清單，
 * 不是猜的。`source` 值定義在各個 collector 裡。
 *
 * ⚠️ 這裡的 url 是**資料集的官方頁面**，用來讓人回頭查證，不是 API endpoint。
 * 查不到穩定官方頁面的就放 null —— 寧可沒有連結，也不要放一個可能失效或錯誤的。
 * 沒有 url 時仍然會標出機關名稱與本地檔案路徑，來源不會完全沒有交代。
 */
export const SOURCE_REGISTRY: Readonly<Record<string, SourceRegistryEntry>> = {
  moi_household_registration: {
    organization: '內政部戶政司',
    datasetLabel: '戶籍人口統計（含年齡別人口數、遷入遷出）',
    kind: 'dataset',
    url: 'https://www.ris.gov.tw/app/portal/346',
  },
  new_taipei_real_estate_open_data: {
    organization: '新北市政府地政局',
    datasetLabel: '不動產成交案件實際資訊（實價登錄）',
    kind: 'dataset',
    url: 'https://data.ntpc.gov.tw/',
  },
  taiwanjobs: {
    organization: '勞動部勞動力發展署（台灣就業通）',
    datasetLabel: '公立就業服務機構求才職缺',
    kind: 'dataset',
    url: 'https://job.taiwanjobs.gov.tw/',
  },
  mol_talent_demand: {
    organization: '勞動部',
    datasetLabel: '重點產業人才需求調查',
    kind: 'dataset',
    url: 'https://data.gov.tw/',
  },
  mol_training_numbers: {
    organization: '勞動部勞動力發展署',
    datasetLabel: '職前訓練課程與訓練人次',
    kind: 'dataset',
    url: 'https://www.wda.gov.tw/',
  },
  mol_vocational_courses: {
    organization: '勞動部勞動力發展署',
    datasetLabel: '職業訓練課程',
    kind: 'dataset',
    url: 'https://www.wda.gov.tw/',
  },
  ntpc_social_affairs_babysitting: {
    organization: '新北市政府社會局',
    datasetLabel: '居家托育服務中心與托育機構',
    kind: 'dataset',
    url: 'https://data.ntpc.gov.tw/',
  },
  ntpc_youth_bureau_budget: {
    organization: '新北市政府青年局',
    datasetLabel: '青年局年度預算書（計畫及預算統計表）',
    kind: 'document',
    url: 'https://www.youth.ntpc.gov.tw/',
  },
  /**
   * analytics published snapshot 的彙總指標。
   *
   * 這一筆的 `organization` 刻意**不是**某個政府機關，而是本專案的資料管線。
   * 這點很重要：`opportunityIndex`、`house_price_median` 這些數字是我們自己用
   * Deterministic Analytics 算出來的，不是任何機關發布的官方統計。把它標成
   * 「內政部戶政司」會是嚴重的錯誤標註 —— 使用者會以為那是官方認證的指標，
   * 拿去引用卻查不到出處。
   *
   * 上游的原始資料是哪些機關，記在每一筆 evidence 的 `computation`
   * （`upstream=population,job_vacancies,…`），可以往回追。
   */
  newtaipei_youth_analytics: {
    organization: '本專案資料管線（非官方發布統計）',
    datasetLabel: '青年機會與留才風險彙總指標',
    kind: 'dataset',
    url: null,
  },
};

/** 每個來源最多列幾個逐筆網址，避免回應被大量連結淹掉。 */
const MAX_RECORD_URLS_PER_SOURCE = 3;

/**
 * 從「實際被 basis 引用的 evidence」推導出資料來源清單。
 *
 * 為什麼只算被引用的、不是全部 evidence：context 裡可能塞了 60 筆 evidence，
 * 但模型只用了其中 5 筆。把沒用到的來源也列出來，會讓使用者以為某個機關的資料
 * 支持了某個結論 —— 那是另一種形式的不誠實。
 *
 * `includeUncited` 為 true 時會把未引用的來源也列出（標在 datasets 但
 * citedEvidenceIds 為空），給「想知道這次可用資料範圍」的情境用。
 */
export function collectSourceAttributions(
  evidence: readonly AiEvidence[],
  output: Pick<StructuredOutput, 'basis'>,
  options: { includeUncited?: boolean } = {},
): SourceAttribution[] {
  const citedIds = new Set(output.basis.map((citation) => citation.evidenceId));
  const relevant = options.includeUncited
    ? evidence
    : evidence.filter((item) => citedIds.has(item.evidenceId));

  const grouped = new Map<string, AiEvidence[]>();
  for (const item of relevant) {
    // source 缺失時用 dataset 名稱兜，總比讓來源整筆消失好。
    const key = item.source ?? `dataset:${item.dataset}`;
    const bucket = grouped.get(key);
    if (bucket) {
      bucket.push(item);
    } else {
      grouped.set(key, [item]);
    }
  }

  return [...grouped.entries()]
    .map(([sourceId, items]) => buildAttribution(sourceId, items, citedIds))
    .sort((left, right) => left.sourceId.localeCompare(right.sourceId));
}

function buildAttribution(
  sourceId: string,
  items: readonly AiEvidence[],
  citedIds: ReadonlySet<string>,
): SourceAttribution {
  const registry = SOURCE_REGISTRY[sourceId];
  // registry 沒登記時，仍然以 evidence 自己帶的 sourceKind 為準，不要硬歸成 dataset。
  const kind = registry?.kind ?? items[0]?.sourceKind ?? 'dataset';

  return {
    sourceId,
    organization: registry?.organization ?? null,
    datasetLabel: registry?.datasetLabel ?? null,
    kind,
    url: registry?.url ?? null,
    recordUrls: unique(items.map((item) => item.sourceUrl)).slice(0, MAX_RECORD_URLS_PER_SOURCE),
    datasets: unique(items.map((item) => item.dataset)),
    citedEvidenceIds: items.map((item) => item.evidenceId).filter((id) => citedIds.has(id)),
    sourcePaths: unique(items.map((item) => item.sourcePath)),
    fetchedAt: latest(items.map((item) => item.fetchedAt)),
  };
}

/**
 * 從實際被 `webReferences` 引用的網路搜尋結果推導來源清單。
 *
 * 跟 `collectSourceAttributions` 分開的原因跟型別分開一樣：網路來源的
 * `kind` 一律是 `'web'`，前端要能一眼分辨哪些是官方統計、哪些是網路補充。
 *
 * 另外這也是 AWS 的使用條款要求：使用 Web Search 時必須保留並顯示來源引用與連結。
 * 所以這個函式不是選配。
 */
export function collectWebSourceAttributions(
  findings: readonly WebFinding[],
  output: Pick<StructuredOutput, 'webReferences'>,
): SourceAttribution[] {
  const citedIds = new Set(output.webReferences.map((reference) => reference.findingId));
  const cited = findings.filter((finding) => citedIds.has(finding.findingId));

  return cited.map((finding) => ({
    // 用網域當 sourceId，這樣同一個網站的多筆結果會歸在一起，
    // 而且前端可以顯示「這來自 youth.ntpc.gov.tw」讓人判斷可信度。
    sourceId: safeHostname(finding.url),
    organization: null,
    datasetLabel: finding.title,
    kind: 'web' as const,
    url: finding.url,
    recordUrls: [finding.url],
    datasets: [],
    citedEvidenceIds: [finding.findingId],
    sourcePaths: [],
    // 用取得時間而不是發布日期：使用者要判斷的是「這份資料多新」。
    fetchedAt: finding.retrievedAt,
  }));
}

function safeHostname(url: string): string {
  try {
    return new URL(url).hostname;
  } catch {
    return 'unknown-web-source';
  }
}

/**
 * 把來源清單轉成一行一筆的文字，給 CLI、log 或純文字呈現用。
 * 前端應該用結構化的 `SourceAttribution[]` 自己排版，不要剖析這段文字。
 */
export function formatSourceAttributions(sources: readonly SourceAttribution[]): string {
  if (sources.length === 0) {
    return '（本次回應沒有引用任何資料來源）';
  }
  return sources
    .map((source) => {
      const who = source.organization ?? source.sourceId;
      const what = source.datasetLabel ?? source.datasets.join('、');
      const link = source.recordUrls[0] ?? source.url;
      const when = source.fetchedAt ? `，資料抓取時間 ${source.fetchedAt}` : '';
      return `- ${who}／${what}${link ? `（${link}）` : ''}${when}`;
    })
    .join('\n');
}

function unique(values: readonly (string | null)[]): string[] {
  return [...new Set(values.filter((value): value is string => value !== null && value.length > 0))];
}

/** ISO 8601 字串可以直接字串比大小，不需要 parse 成 Date。 */
function latest(values: readonly (string | null)[]): string | null {
  const present = values.filter((value): value is string => value !== null);
  return present.length === 0 ? null : present.reduce((max, value) => (value > max ? value : max));
}
