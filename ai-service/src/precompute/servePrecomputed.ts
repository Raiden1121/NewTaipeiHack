/**
 * 用預先算的結果回應 explain / policyCopilot，沒有就即時算。
 */
import type { BedrockClient } from '../bedrock/client.js';
import type { AiRequestContext } from '../types/aiEvidence.js';
import type { WebSearchProvider } from '../websearch/provider.js';
import type { AiFeatureResult } from '../handlers/runFeature.js';
import { contextFingerprint } from './fingerprint.js';
import {
  DisabledPrecomputedStore,
  type PrecomputedEntry,
  type PrecomputedStore,
} from './store.js';

/**
 * - `hit`：回的是預先算好的結果
 * - `miss`：快取開著但沒有這筆，已即時計算
 * - `disabled`：沒設 `AI_PRECOMPUTE_DIR`
 * - `bypass`：這個 action 不快取（Q&A）
 *
 * 這個欄位會出現在 API 回應裡。**不能省。** 少了它，demo 當天看到一份內容不
 * 對的卡片時，沒辦法分辨是「模型這次答得不好」還是「回了上一個快照的舊答案」，
 * 而這兩件事的處理方向完全不同。
 */
export type PrecomputeCacheStatus = 'hit' | 'miss' | 'disabled' | 'bypass';

export interface PrecomputedDispatchResult extends AiFeatureResult {
  cache: PrecomputeCacheStatus;
  /** `bypass` 與 `disabled` 時是 null。 */
  fingerprint: string | null;
  /** 命中時是這份結果**當初產生**的時間，不是現在。 */
  precomputedAt: string | null;
}

/**
 * 可以預先算的 action。
 *
 * Q&A 不在裡面，而且不是因為「還沒做」：它的輸出取決於使用者當下打的問題，
 * 問法有無限多種，預先算不可能涵蓋。硬要快取的話命中率趨近於零，
 * 只是白繞一圈。
 */
export const PRECOMPUTABLE_ACTIONS = ['explain', 'policyCopilot'] as const;
export type PrecomputableAction = (typeof PRECOMPUTABLE_ACTIONS)[number];

export function isPrecomputable(action: string): action is PrecomputableAction {
  return (PRECOMPUTABLE_ACTIONS as readonly string[]).includes(action);
}

export interface PrecomputeOptions {
  store?: PrecomputedStore;
  webSearch?: WebSearchProvider;
  /**
   * miss 之後要不要把算出來的結果寫回快取。
   *
   * 預設 **false**。看起來寫回去是好事，但那會讓「第一個打進來的使用者」
   * 決定所有人之後看到的卡片內容 —— 包含模型那次剛好答得比較差的版本，
   * 而且沒有人會知道。批次腳本產生的結果至少是可以重跑、可以檢查的。
   * 要開就用 `AI_PRECOMPUTE_WRITE_THROUGH=1`，並且知道自己在做什麼。
   */
  writeThrough?: boolean;
  /** 寫回快取時要記的快照 id（批次腳本知道，request 路徑不知道）。 */
  snapshotId?: string | null;
}

/**
 * action 用泛型而不是寫死 `string`：呼叫端的 `dispatch` 收的是
 * `'explain' | 'policyCopilot' | 'qa'` 這個聯集，如果這裡宣告成 `string`，
 * 傳進來就會是型別錯誤（`string` 不能賦值給聯集）。泛型讓兩邊對得上，
 * 又不必把 action 清單複製一份到這個模組。
 */
export async function dispatchWithPrecompute<A extends string>(
  action: A,
  dispatchLive: (
    action: A,
    client: BedrockClient,
    context: AiRequestContext,
    webSearch?: WebSearchProvider,
  ) => Promise<AiFeatureResult>,
  client: BedrockClient,
  context: AiRequestContext,
  options: PrecomputeOptions = {},
): Promise<PrecomputedDispatchResult> {
  const store = options.store ?? new DisabledPrecomputedStore();

  if (!isPrecomputable(action)) {
    const live = await dispatchLive(action, client, context, options.webSearch);
    return { ...live, cache: 'bypass', fingerprint: null, precomputedAt: null };
  }
  if (store instanceof DisabledPrecomputedStore) {
    const live = await dispatchLive(action, client, context, options.webSearch);
    return { ...live, cache: 'disabled', fingerprint: null, precomputedAt: null };
  }

  const fingerprint = contextFingerprint(action, context);
  const cached = await store.get(fingerprint);
  if (cached !== null) {
    return {
      output: cached.output,
      sources: cached.sources,
      cache: 'hit',
      fingerprint,
      precomputedAt: cached.generatedAt,
    };
  }

  const startedAt = Date.now();
  const live = await dispatchLive(action, client, context, options.webSearch);
  const elapsedMs = Date.now() - startedAt;

  if (options.writeThrough === true) {
    await store.put(
      buildEntry({
        fingerprint,
        action,
        context,
        client,
        result: live,
        elapsedMs,
        snapshotId: options.snapshotId ?? null,
      }),
    );
  }

  return { ...live, cache: 'miss', fingerprint, precomputedAt: null };
}

/** 組一筆快取條目。批次腳本也用這個，兩邊的欄位才不會長不一樣。 */
export function buildEntry(input: {
  fingerprint: string;
  action: string;
  context: AiRequestContext;
  client: BedrockClient;
  result: AiFeatureResult;
  elapsedMs: number;
  snapshotId: string | null;
}): PrecomputedEntry {
  return {
    fingerprint: input.fingerprint,
    action: input.action,
    focusDistrict: input.context.focusDistrict ?? null,
    focusArea: input.context.focusArea ?? null,
    snapshotId: input.snapshotId,
    generatedAt: new Date().toISOString(),
    generatedBy: input.client.description,
    elapsedMs: input.elapsedMs,
    output: input.result.output,
    sources: input.result.sources,
  };
}
