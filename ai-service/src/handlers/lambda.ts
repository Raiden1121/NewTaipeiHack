import { z } from 'zod';
import { createBedrockClientFromEnv, type BedrockClient } from '../bedrock/client.js';
import { AiRequestContextSchema, type AiRequestContext } from '../types/aiEvidence.js';
import type { StructuredOutput } from '../types/structuredOutput.js';
import type { SourceAttribution } from '../types/sourceAttribution.js';
import { createWebSearchProviderFromEnv } from '../websearch/factory.js';
import type { WebSearchProvider } from '../websearch/provider.js';
import type { AiFeatureResult } from './runFeature.js';
import { explainData } from './explainData.js';
import { policyCopilot } from './policyCopilot.js';
import { dataQa } from './dataQa.js';
import {
  dispatchWithPrecompute,
  type PrecomputeCacheStatus,
} from '../precompute/servePrecomputed.js';
import { createPrecomputedStoreFromEnv } from '../precompute/store.js';

/**
 * 對外的 action 名稱。這份清單是給 backend / frontend 對齊用的契約
 * （決策 B），改動要同步通知，不要單方面加值。
 */
export const AI_ACTIONS = ['explain', 'policyCopilot', 'qa'] as const;
export const AiActionSchema = z.enum(AI_ACTIONS);
export type AiAction = z.infer<typeof AiActionSchema>;

/** request payload：`{ action, context }`。context 就是 `AiRequestContext`。 */
export const AiRequestSchema = z.object({
  action: AiActionSchema,
  context: AiRequestContextSchema,
});
export type AiRequest = z.infer<typeof AiRequestSchema>;

/**
 * response payload。
 *
 * 刻意不直接回 `StructuredOutput`，而是包一層 envelope：前端需要知道
 * 「這是真模型還是 mock」（`generatedBy`），否則 demo 當天忘記設環境變數時，
 * 畫面上看不出來拿到的是假分析。
 */
export interface AiSuccessResponse {
  action: AiAction;
  generatedBy: string;
  /**
   * 這份結果是預先算的還是即時算的。
   *
   * `hit` 代表回的是批次產生的結果，`precomputedAt` 是它**當初**產生的時間。
   * explain 與 policyCopilot 實測各要 50 與 58 秒，超過 API Gateway HTTP API
   * 固定的 30 秒上限，所以正式路徑應該讓它們走預先算。
   *
   * 前端該把 `precomputedAt` 顯示出來（例如「分析產生於 X」）：使用者看到的
   * 卡片可能是幾小時前算的，不講就等於暗示它是剛剛算的。
   */
  cache: PrecomputeCacheStatus;
  precomputedAt: string | null;
  output: StructuredOutput;
  /**
   * 資料來源。**每個回應都一定會有這個欄位**（沒有引用任何資料時是空陣列，
   * 那種情況 `output.dataSufficiency` 會是 `insufficient`）。
   *
   * 由程式從實際被 `output.basis` 引用的 evidence 推導，模型碰不到，
   * 所以不會有捏造的機關名稱或網址。前端應該直接渲染這個結構，
   * 不要去剖析 `output` 裡的中文找來源。
   */
  sources: SourceAttribution[];
}

export interface AiErrorResponse {
  error: string;
  /** zod 驗證失敗時的逐欄位訊息，方便呼叫端定位問題。 */
  issues?: { path: string; message: string }[];
}

/**
 * API Gateway proxy integration 與 Lambda Function URL 共通的最小 event 形狀。
 * 只用得到 `body`，所以不綁 `@types/aws-lambda`。
 */
interface LambdaEvent {
  body?: string | null;
  /**
   * API Gateway / Function URL 在某些設定下會把 body 用 base64 包起來
   * （例如 binary media types 設成通用萬用字元時）。沒處理的話會得到
   * 「request body 不是有效的 JSON」，然後花很久才想到是編碼問題。
   */
  isBase64Encoded?: boolean;
}

interface LambdaResponse {
  statusCode: number;
  headers: Record<string, string>;
  body: string;
}

/**
 * 最小可用的 Lambda handler，給 API Gateway 呼叫。
 *
 * ⚠️ **目前沒有任何 authentication / authorization。** 黑客松內部呼叫可以接受，
 * 但如果要掛成公開的 Function URL 或 API Gateway endpoint，等於把 Bedrock 的
 * 帳單開放給任何人呼叫（每次請求都會送出完整 prompt）。上線前必須先加上
 * API key、IAM 或 Cognito 授權，這件事要跟 backend 一起決定（見
 * `backend/backend.md` 的 Boundaries）。
 */
export async function handler(event: LambdaEvent): Promise<LambdaResponse> {
  try {
    const request = AiRequestSchema.parse(parseBody(event.body, event.isBase64Encoded));
    const client = createBedrockClientFromEnv();
    const webSearch = createWebSearchProviderFromEnv();
    // explain / policyCopilot 先查預先算的結果；Q&A 一律即時（問法無限多種，
    // 預先算不可能涵蓋）。沒設 AI_PRECOMPUTE_DIR 時行為完全等於沒有快取。
    const result = await dispatchWithPrecompute(request.action, dispatch, client, request.context, {
      store: createPrecomputedStoreFromEnv(),
      webSearch,
      writeThrough: process.env.AI_PRECOMPUTE_WRITE_THROUGH === '1',
    });

    return jsonResponse(200, {
      action: request.action,
      generatedBy: client.description,
      cache: result.cache,
      precomputedAt: result.precomputedAt,
      output: result.output,
      sources: result.sources,
    } satisfies AiSuccessResponse);
  } catch (error) {
    if (error instanceof z.ZodError) {
      return jsonResponse(400, {
        error: '請求格式不符合 AiRequestSchema',
        issues: error.issues.map((issue) => ({
          path: issue.path.join('.') || '(root)',
          message: issue.message,
        })),
      } satisfies AiErrorResponse);
    }
    // 格式沒問題但執行失敗（Bedrock 不可用、驗證重試用盡、引用了不存在的
    // evidenceId…）是伺服器端問題，不該回 400 讓呼叫端以為是自己傳錯。
    return jsonResponse(502, {
      error: error instanceof Error ? error.message : 'unknown error',
    } satisfies AiErrorResponse);
  }
}

export function dispatch(
  action: AiAction,
  client: BedrockClient,
  context: AiRequestContext,
  webSearch?: WebSearchProvider,
): Promise<AiFeatureResult> {
  switch (action) {
    case 'explain':
      return explainData(client, context, webSearch);
    case 'policyCopilot':
      return policyCopilot(client, context, webSearch);
    case 'qa':
      return dataQa(client, context, webSearch);
    default: {
      const exhaustive: never = action;
      throw new Error(`未知的 action: ${String(exhaustive)}（合法值：${AI_ACTIONS.join(' / ')}）`);
    }
  }
}

function parseBody(body: string | null | undefined, isBase64Encoded = false): unknown {
  if (body === null || body === undefined || body.length === 0) {
    return {};
  }
  const decoded = isBase64Encoded ? Buffer.from(body, 'base64').toString('utf-8') : body;
  try {
    return JSON.parse(decoded);
  } catch {
    throw new z.ZodError([
      { code: z.ZodIssueCode.custom, path: ['body'], message: 'request body 不是有效的 JSON' },
    ]);
  }
}

function jsonResponse(statusCode: number, payload: unknown): LambdaResponse {
  return {
    statusCode,
    headers: { 'content-type': 'application/json; charset=utf-8' },
    body: JSON.stringify(payload),
  };
}
