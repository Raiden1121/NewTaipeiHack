import { z } from 'zod';
import { createBedrockClientFromEnv, type BedrockClient } from '../bedrock/client.js';
import { AiRequestContextSchema, type AiRequestContext } from '../types/aiEvidence.js';
import type { StructuredOutput } from '../types/structuredOutput.js';
import type { SourceAttribution } from '../types/sourceAttribution.js';
import { WebSearchScopeSchema } from '../types/webFinding.js';
import { createWebSearchProviderFromEnv } from '../websearch/factory.js';
import type { WebSearchProvider } from '../websearch/provider.js';
import { buildAiContext, createEvidenceRepositoryFromEnv } from '../context/buildContext.js';
import type { EvidenceRepository } from '../context/evidenceRepository.js';
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

/**
 * 自撈路徑的搜尋設定覆寫。
 *
 * 刻意**不用** `WebSearchSettingsSchema`：那份 schema 每個欄位都有 `.default()`，
 * 所以只傳 `{ enabled: true }` 也會被補成 `scope: 'all'`。那會蓋掉伺服器端的
 * `WEB_SEARCH_SCOPE=trusted` —— 呼叫端沒表達過的意見被當成明確選擇。
 * 這裡全部 optional、沒有預設，對應 `BuildAiContextOptions.webSearch`
 * 的 `Partial<WebSearchSettings>`，沒講的欄位就交給 `buildAiContext` 決定。
 */
const WebSearchOverrideSchema = z.object({
  enabled: z.boolean().optional(),
  contextSize: z.enum(['low', 'medium', 'high']).optional(),
  scope: WebSearchScopeSchema.optional(),
});

/**
 * request payload。**兩種形狀都接受**：
 *
 * 1. `{ action, context }` —— 呼叫端自己組好 evidence（原本唯一的形狀，行為不變）
 * 2. `{ action, focusDistrict, focusArea, question? }` —— 省略 `context`，
 *    由 ai-service 自己去 evidence 來源撈（需要設 `AI_EVIDENCE_SOURCE`）
 *
 * ## 為什麼要有第二種
 *
 * 第一種要求呼叫端產生完整的 `AiEvidence[]`，包含 `evidenceId`、`unit`、
 * `youthEligibility`、`computation`。那些值來自 `src/context/` 的 3,600 行
 * （攤平規則、`ANALYTICS_METRIC_META` 的 165 個指標、`BLOCKED_KEYS`、dedupe），
 * 而 backend 是 Python —— 等於要用另一個語言重寫一份並**逐字節產生相同的結果**。
 *
 * 而且失敗方式很惡劣：預先算的快取鍵是輸入指紋，含每筆 evidence 的
 * `evidenceId` + `value` + `unit`（見 `precompute/fingerprint.ts`）。
 * 兩個實作只要差一個字元（例如 metricId 少了巢狀前綴，`years.people_total`
 * 而不是 `annual.population.people_total`），指紋就永遠不同 → 永遠 miss →
 * explain / policyCopilot 走即時算 50–58 秒 → 被 API Gateway 的 30 秒切斷。
 * 兩邊都「有資料、跑得動」，只是使用者永遠拿到 503，沒有任何錯誤訊息指向真因。
 *
 * 第二種讓組 evidence 這件事只有一份實作，而且跟 `npm run precompute` 是**同一份**
 * （都走 `createEvidenceRepositoryFromEnv()` + `buildAiContext()`），
 * 所以指紋在結構上不可能分岔。
 */
export const AiRequestSchema = z.object({
  action: AiActionSchema,
  /** 呼叫端組好的 context。省略時走自撈。 */
  context: AiRequestContextSchema.optional(),
  /**
   * 以下三個只在**省略 `context`** 時使用；有 `context` 時一律以 context 裡的值為準
   * （不做合併，避免同一個欄位有兩個來源時行為要靠猜）。
   */
  focusDistrict: z.string().nullish(),
  focusArea: z.string().nullish(),
  question: z.string().nullish(),
  /**
   * 省略時**不傳給 `buildAiContext`**，讓它用自己的預設（搜尋開啟）。
   *
   * 這件事對 explain / policyCopilot 是必要的：`runBatch.ts` 也沒傳，
   * 所以兩邊的 `webSearch.enabled` 都是 `true`。這裡若改成吃
   * `AiRequestContextSchema` 的預設（`false`），指紋就會跟預先算的結果永遠不同。
   */
  webSearch: WebSearchOverrideSchema.optional(),
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
    const context = await resolveRequestContext(request);
    const client = createBedrockClientFromEnv();
    const webSearch = createWebSearchProviderFromEnv();
    // explain / policyCopilot 先查預先算的結果；Q&A 一律即時（問法無限多種，
    // 預先算不可能涵蓋）。沒設 AI_PRECOMPUTE_DIR 時行為完全等於沒有快取。
    const result = await dispatchWithPrecompute(request.action, dispatch, client, context, {
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

/**
 * evidence 來源。**跨呼叫重用**（module scope 的 lazy singleton）。
 *
 * 不是微優化：`DynamoEvidenceRepository` 會建 DynamoDB client，而實測 1,167 ms 的
 * 讀取裡有相當一部分是 client 初始化與 TLS 交握。Lambda 的 warm invocation 之間
 * 重用同一個 client 才拿得到那個省下來的時間。
 *
 * lazy 而不是在 module top-level 直接建：top-level 會在 import 時就讀環境變數，
 * 於是所有 import 這個模組的測試都得先把環境變數擺好，即使它們根本不走自撈。
 */
let cachedRepository: EvidenceRepository | null = null;

/**
 * 自撈有沒有被啟用。
 *
 * 用「`AI_EVIDENCE_SOURCE` 有沒有設」而不是自己發明一個開關，因為那個變數本來就是
 * 「evidence 從哪來」的唯一控制點，多一個開關只會多一種不一致的狀態。
 * Terraform 在傳了 analytics 表名時會一起設 `AI_EVIDENCE_SOURCE=dynamo`
 * （見 `infrastructure/modules/ai_service/main.tf`），所以部署的 Lambda 是開的。
 *
 * 沒設就**不要**默默退回讀本機快照檔：Lambda 沒有那些檔案，那條路只會在讀檔時
 * 才失敗，而錯誤訊息會指向檔案系統而不是真正的原因（呼叫端沒給 context、
 * 伺服器也沒設定要自己撈）。
 */
export function selfFetchSource(env: NodeJS.ProcessEnv = process.env): string | null {
  const mode = env.AI_EVIDENCE_SOURCE?.trim();
  return mode === undefined || mode === '' ? null : mode;
}

/**
 * 決定這次請求用哪一份 context。
 *
 * 有 `context` 就照用 —— 呼叫端已經組好，這裡不做任何補充或合併。
 * 沒有就自己撈，而且**必須跟 `runBatch.ts` 用完全一樣的呼叫**，否則指紋對不上。
 * 目前 `runBatch` 傳的是 `{ focusDistrict, focusArea }`（沒有 question、
 * 沒有 webSearch），而 `question: null` 與省略 question 在 `buildAiContext` 裡
 * 走同一條分支（`inferFocusMetrics` / `inferComparisonMetrics` 對非字串都回 `[]`，
 * 回傳的 `question` 都是 `null`），所以這裡傳 null 不會讓指紋改變。
 */
export async function resolveRequestContext(
  request: AiRequest,
  env: NodeJS.ProcessEnv = process.env,
): Promise<AiRequestContext> {
  if (request.context !== undefined) {
    return request.context;
  }

  const source = selfFetchSource(env);
  if (source === null) {
    throw new Error(
      '請求沒有帶 context.evidence，而這個服務沒有被設定成自己去撈 evidence。' +
        '兩種修法選一個：呼叫端送完整的 `context`（含 evidence），' +
        '或在伺服器端設 AI_EVIDENCE_SOURCE（線上應為 `dynamo`，並一併設 ANALYTICS_TABLE_NAME）。',
    );
  }

  cachedRepository ??= createEvidenceRepositoryFromEnv(env);
  return buildAiContext(cachedRepository, {
    focusDistrict: request.focusDistrict ?? null,
    focusArea: request.focusArea ?? null,
    question: request.question ?? null,
    // 沒傳就不要傳 —— 讓 buildAiContext 用它自己的預設（搜尋開啟），
    // 那才跟 runBatch 一致。傳 `undefined` 進去也會被 `webSearch?.enabled ?? true`
    // 當成沒傳，但明確不放這個 key 讀起來不會讓人以為有覆寫。
    ...(request.webSearch === undefined ? {} : { webSearch: request.webSearch }),
  });
}

/** 測試用：清掉 repository 快取，讓下一次 `resolveRequestContext` 重新依環境變數建。 */
export function resetEvidenceRepositoryCache(): void {
  cachedRepository = null;
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
