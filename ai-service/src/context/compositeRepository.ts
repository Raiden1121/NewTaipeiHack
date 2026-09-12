import type { AiEvidence } from '../types/aiEvidence.js';
import {
  HOUSING_AGGREGATE_METRIC_IDS,
  TRANSACTION_LEVEL_NOTE,
  TRANSACTION_LEVEL_SUPERSEDED_NOTE,
  type EvidenceBundle,
  type EvidenceQuery,
  type EvidenceRepository,
} from './evidenceRepository.js';

/**
 * 把多個 evidence 來源併成一個。
 *
 * 目前的用途是 curated（原始資料點）＋ analytics（彙總指標）一起給 AI。
 * 兩者缺一都會讓分析瘸腿：
 *
 * - 只有 curated：模型看得到 3,896 筆職缺明細，卻沒有「每萬青年職缺數」，
 *   於是要嘛不敢下判斷，要嘛偷偷自己算（違反邊界）。
 * - 只有 analytics：模型看得到「機會指數 45.3 分」，卻沒有任何原始資料點
 *   可以說明這個分數背後是什麼，也拿不到青年局預算的逐筆網址。
 *
 * 併起來之後 `metricSource` 就是模型判斷「這個數字能不能代表全區」的依據，
 * 這也是 guardrails 規則 7 存在的原因。
 *
 * ## 一個來源掛掉不會讓整個請求失敗
 *
 * 這是刻意的：analytics 快照還沒發布、或 curated 還沒跑過，都是本機開發與
 * demo 前很常見的狀態。任何一邊讀不到就整個 502，會讓另一邊明明有資料卻
 * 用不到。改成把失敗原因寫進 notes（也就是輸出的 limitations），讓使用者看到
 * 「本次只有其中一種資料」—— 誠實降級，不是靜默降級。
 */
export class CompositeEvidenceRepository implements EvidenceRepository {
  readonly description: string;

  constructor(private readonly repositories: readonly EvidenceRepository[]) {
    if (repositories.length === 0) {
      throw new Error('CompositeEvidenceRepository 至少需要一個 repository');
    }
    this.description = `composite(${repositories.map((repo) => repo.description).join(' + ')})`;
  }

  async query(query: EvidenceQuery): Promise<EvidenceBundle> {
    const evidence: AiEvidence[] = [];
    const notes: string[] = [];
    let totalMatched = 0;
    let truncated = false;
    let succeeded = 0;

    for (const repository of this.repositories) {
      try {
        const bundle = await repository.query(query);
        evidence.push(...bundle.evidence);
        notes.push(...bundle.notes);
        totalMatched += bundle.totalMatched;
        truncated = truncated || bundle.truncated;
        succeeded += 1;
      } catch (error) {
        notes.push(
          `evidence 來源 ${repository.description} 讀取失敗，本次回應不含這個來源的資料` +
            `（原因：${error instanceof Error ? error.message : String(error)}）。`,
        );
      }
    }

    if (succeeded === 0) {
      // 全部都掛了才是真的錯誤。這時候不能回空 bundle 假裝「查無資料」——
      // 「沒有資料」與「讀不到資料」對使用者是不同的意思。
      throw new Error(
        `所有 evidence 來源都讀取失敗：${notes.join(' ')}`,
      );
    }

    return {
      evidence,
      totalMatched,
      truncated,
      notes: reconcileNotes(notes, evidence),
    };
  }
}

/**
 * 修掉合併後互相矛盾的限制說明。
 *
 * 目前只有一條，但它是真實踩到的：curated repository 一律會加上
 * `TRANSACTION_LEVEL_NOTE`（「居住負擔面向缺漏」），因為它自己確實排除了
 * house_prices / rentals。但 analytics 已經提供各區房價與租金中位數，
 * 所以合併後那句話是錯的。
 *
 * 為什麼在這一層修：curated repository 不知道 analytics 存在，也不該知道 ——
 * 它的職責就只是「我這邊有什麼、我排除了什麼」。只有合併的人才有完整資訊
 * 判斷哪些限制已經被另一個來源補上了。
 */
export function reconcileNotes(
  notes: readonly string[],
  evidence: readonly AiEvidence[],
): string[] {
  const hasHousingAggregate = evidence.some(
    (item) =>
      item.metricSource === 'analytics_metric' &&
      HOUSING_AGGREGATE_METRIC_IDS.includes(lastMetricSegment(item.metricId)),
  );

  const reconciled = notes.map((note) =>
    hasHousingAggregate && note === TRANSACTION_LEVEL_NOTE ? TRANSACTION_LEVEL_SUPERSEDED_NOTE : note,
  );

  return [...new Set(reconciled)];
}

function lastMetricSegment(metricId: string): string {
  const withoutLabel = metricId.split('#')[0] ?? metricId;
  return withoutLabel.split('.').pop() ?? withoutLabel;
}
