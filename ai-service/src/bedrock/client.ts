import {
  BedrockRuntimeClient,
  ConverseCommand,
  type ContentBlock,
  type ConverseCommandInput,
  type Message,
} from '@aws-sdk/client-bedrock-runtime';
import { z } from 'zod';
import { DISCLAIMER_KEYWORD, type StructuredOutput } from '../types/structuredOutput.js';
import { KNOWN_LIMITATIONS_HEADER } from '../prompts/guardrails.js';
import { QA_OUTPUT_SCHEMA_NAME } from '../types/structuredOutputJsonSchema.js';
import {
  SIX_BLOCK_OUTPUT_SPEC,
  type OutputSchemaSpec,
  type PromptPayload,
} from '../prompts/promptPayload.js';
import { resolveBedrockEnv, type BedrockAuthMode } from './env.js';

export interface BedrockClient {
  /** 給錯誤訊息與日誌用的描述，例如 `bedrock(us.anthropic.claude-sonnet-4-*, us-east-1)` */
  readonly description: string;
  invokeStructured(payload: PromptPayload): Promise<StructuredOutput>;
}

/**
 * 本機開發／測試用的假 client，不打任何網路、不需要 AWS 權限。
 *
 * 回傳內容刻意每一句都標 `[mock]`：如果 demo 當天忘記設環境變數，畫面上會直接
 * 看得出來是假資料，而不是拿一段看起來很像真的分析上台。
 */
export class MockBedrockClient implements BedrockClient {
  readonly description = 'mock(no network)';

  async invokeStructured(payload: PromptPayload): Promise<StructuredOutput> {
    const evidenceIds = extractEvidenceIds(payload.user);
    const findingIds = extractFindingIds(payload.user);
    // 純網路的情況（管線沒資料但有搜尋結果）必須產出對應形狀的輸出，
    // 否則 mock 模式下測不到那條路徑的不變式。
    const webOnly = evidenceIds.length === 0 && findingIds.length > 0;

    const limitations = [
      '[mock] 目前使用 MockBedrockClient，尚未呼叫真實模型，這段內容不是對資料的實際分析。',
      ...extractKnownLimitations(payload.user),
    ];
    if (webOnly) {
      // schema 強制：純網路回答必須明講沒有官方統計支撐。
      limitations.push('[mock] 本次沒有資料管線的官方統計，以下內容僅來自網路搜尋，未經驗證。');
    }

    // mock 也要跟著這次要求的格式走，否則 Q&A 的路徑在 mock 模式下等於沒被測到
    // （會拿到一份沒有 answer 的六塊輸出，而真模型會給 answer）。
    const outputSchema = payload.outputSchema ?? SIX_BLOCK_OUTPUT_SPEC;
    const isQa = outputSchema.name === QA_OUTPUT_SCHEMA_NAME;

    return outputSchema.parse({
      answer: isQa
        ? '[mock] 尚未接上 Bedrock，這是 MockBedrockClient 的佔位回答，不是對資料的實際分析。'
        : null,
      // 刻意只給 missingForQuestion，跟真模型現在的行為一致：
      // availableMetrics / youthSpecificMetrics / contextOnlyMetrics 由程式盤點
      // （見 handlers/evidenceInventory.ts），模型與 mock 都不輸出。
      // mock 如果自己填了那三個欄位，就會蓋掉真實路徑，讓「程式盤點」這件事在
      // mock 模式下測不到。
      evidenceReview: {
        // 非空是刻意的：這同時讓 dataSufficiency 不可能是 sufficient，
        // 跟下面那一行的理由一致。
        missingForQuestion: ['[mock] 未實際盤點 evidence，這是 MockBedrockClient 的佔位內容。'],
      },
      // partial 而不是 sufficient：mock 沒有真的分析資料，宣稱資料充足會讓
      // 「資料不足會誠實標示」這件事在 mock 模式下測起來是假綠燈。
      dataSufficiency: 'partial',
      // Q&A 走 answer，四塊留空 —— 這正是真模型在「純查值問題」時該有的行為，
      // mock 也照著做，這樣 mock 模式下看到的形狀跟真模型一致。
      issues: isQa
        ? []
        : ['[mock] 尚未接上 Bedrock，這是 MockBedrockClient 回傳的假資料，僅供介面測試用。'],
      strengths: [],
      resourceGaps: [],
      policyDirections: [],
      // 有 evidence 就引用第一筆；沒有就留空（不可以把 findingId 塞進 basis）。
      basis: evidenceIds.length > 0
        ? [{ evidenceId: evidenceIds[0], note: '[mock] 佔位引用，非真實模型判斷' }]
        : [],
      // 只在沒有 evidence 時才引用網路來源。有 evidence 時保持空陣列，
      // 讓「網路引用必須可追溯」的驗證測到的是真實行為而不是 mock 的習慣。
      webReferences: webOnly
        ? [{ findingId: findingIds[0], note: '[mock] 根據網路資料的佔位引用' }]
        : [],
      limitations,
      disclaimer: `[mock] AI 建議屬於政策輔助資訊，${DISCLAIMER_KEYWORD}。`,
    });
  }
}

export interface BedrockRuntimeAdapterOptions {
  modelId: string;
  region: string;
  /**
   * Bedrock API key（`ABSK` 開頭）。有給且 authMode 是 bearer 時走 bearer 認證，
   * 不依賴 `AWS_ACCESS_KEY_ID` 那組憑證。
   */
  apiKey?: string | null;
  /** 預設 sigv4（維持 AWS SDK 原本的優先順序）。 */
  authMode?: BedrockAuthMode;
  /** 六塊中文輸出可能不短；預設 4096。 */
  maxTokens?: number;
  /** 這是「引用資料做解讀」而不是創作，預設 0 以求可重現。 */
  temperature?: number;
  /**
   * 是否使用 Bedrock 原生 structured outputs（`outputConfig.textFormat`）。
   * 預設 true。設 false 時只靠 prompt 要求 JSON，並自己從文字裡剖析。
   */
  useStructuredOutputs?: boolean;
  /**
   * zod 驗證失敗時最多再試幾次（把錯誤訊息回饋給模型要它修）。預設 2（共 2 次呼叫）。
   *
   * 為什麼需要：Bedrock structured outputs 只保證形狀，不保證 disclaimer 有沒有含
   * 固定字樣、basis 引用的 evidenceId 是否真的存在。這些語意規則只能靠事後驗證 + 重試。
   */
  maxAttempts?: number;
  /** 讓測試可以注入假的 client。 */
  client?: Pick<BedrockRuntimeClient, 'send'>;
}

/**
 * 真的呼叫 Amazon Bedrock 的實作。
 *
 * 用 Converse API ＋ 原生 structured outputs（`outputConfig.textFormat`），
 * 而不是「在 prompt 裡拜託模型回 JSON 然後自己剖析」：後者在 demo 現場最常見的
 * 失敗模式就是模型多包了一層 markdown code fence 或多寫一句開場白，JSON.parse 就炸。
 *
 * 驗證是兩道關卡（見 `types/structuredOutputJsonSchema.ts` 的說明）：
 * Bedrock 保證形狀，`StructuredOutputSchema` 保證語意。第二道失敗時會把 zod 的
 * 錯誤訊息回饋給模型要它修，而不是直接把不合格的內容丟給前端。
 */
/**
 * 輸出 token 上限的預設值。
 *
 * 這個值調過兩次，兩次都是被真實資料打出來的：
 *
 * **4096 → 8192**：接上 analytics 的彙總指標之後，一個行政區的 context 有 250 筆
 * evidence，模型寫出來的六塊輸出（含每條結論的 basis 引用）超過 4096 token，
 * **JSON 在中途被截斷**。失敗訊息長得像
 * `Expected ',' or ']' after array element in JSON at position 8045`，
 * 完全看不出是 maxTokens 造成的 —— 第一次遇到時我以為是 Bedrock 連線掛住了。
 *
 * **8192 → 16384**：8192 只夠 Data Explanation 與 Q&A，**Policy Copilot 會時好時壞**。
 * 它是三個功能裡輸出最長的（實測 issues 6 條、strengths 6 條、resourceGaps 3 條、
 * policyDirections 4 條，加上 31 條 basis 引用，每條都帶一句中文說明），
 * 而中文的 token 密度比英文高。同一個請求在 8192 之下跑過一次成功、一次截斷 ——
 * 這種間歇性失敗比穩定失敗更糟，demo 當天不會知道哪一次會壞。
 *
 * 提高上限本身不會增加成本（Bedrock 是按實際產出的 token 計費），只會讓最壞情況
 * 的延遲變長 —— 而延遲的解法是換模型，不是把輸出砍斷。
 *
 * 可以用 `BEDROCK_MAX_TOKENS` 覆寫。
 */
export const DEFAULT_MAX_TOKENS = 16384;

export class BedrockRuntimeAdapter implements BedrockClient {
  readonly description: string;
  private readonly client: Pick<BedrockRuntimeClient, 'send'>;
  private readonly modelId: string;
  private readonly maxTokens: number;
  private readonly temperature: number;
  private readonly useStructuredOutputs: boolean;
  private readonly maxAttempts: number;

  constructor(options: BedrockRuntimeAdapterOptions) {
    this.modelId = options.modelId;
    this.maxTokens = options.maxTokens ?? DEFAULT_MAX_TOKENS;
    this.temperature = options.temperature ?? 0;
    this.useStructuredOutputs = options.useStructuredOutputs ?? true;
    this.maxAttempts = Math.max(1, options.maxAttempts ?? 2);
    const authMode = options.authMode ?? 'sigv4';
    this.client = options.client ?? buildRuntimeClient(options, authMode);
    this.description = `bedrock(${options.modelId}, ${options.region}, auth=${authMode})`;
  }

  async invokeStructured(payload: PromptPayload): Promise<StructuredOutput> {
    const messages: Message[] = [{ role: 'user', content: [{ text: payload.user }] }];
    const outputSchema = payload.outputSchema ?? SIX_BLOCK_OUTPUT_SPEC;
    let lastError: unknown;

    for (let attempt = 1; attempt <= this.maxAttempts; attempt += 1) {
      const response = await this.client.send(
        new ConverseCommand(this.buildRequest(payload.system, messages, outputSchema)),
      );
      const text = extractResponseText(response.output?.message?.content);
      if (text === null) {
        throw new Error(
          `Bedrock 回應沒有可用的文字內容（${this.description}，stopReason=${String(response.stopReason)}）。`,
        );
      }

      // 被 maxTokens 截斷時**不要重試**。重試的前提是「模型寫錯了，講清楚它會改」，
      // 但這裡模型沒寫錯 —— 是我們給的輸出空間不夠，同樣的上限再跑一次必然同樣被截斷。
      // 實測這條路徑白花了 4 分多鐘（Opus 兩次各兩分鐘）才吐出一個看不懂的 JSON 剖析錯誤。
      if (response.stopReason === 'max_tokens') {
        throw new Error(
          `Bedrock 回應在寫完之前就達到輸出上限 maxTokens=${this.maxTokens}（${this.description}），` +
            'JSON 因此不完整。這通常表示 context 裡的 evidence 太多、模型要寫的結論太長。' +
            '請調高 BEDROCK_MAX_TOKENS，或減少 evidence 筆數' +
            '（buildAiContext 的 maxEvidence，或用 focusArea 限縮 analytics 的讀取範圍）。',
        );
      }

      try {
        // 用這次 prompt 指定的格式驗證。驗證失敗仍然走原本的修正流程
        // （把錯誤回饋給模型再試一次），所以 Q&A 漏填 answer 時模型有機會補上。
        return outputSchema.parse(parseJsonPayload(text));
      } catch (error) {
        lastError = error;
        if (attempt === this.maxAttempts) {
          break;
        }
        // 把模型自己的回答與具體錯誤一起放回對話，要它針對錯誤修正而不是重寫一次。
        messages.push({ role: 'assistant', content: [{ text }] });
        messages.push({ role: 'user', content: [{ text: buildRepairInstruction(error) }] });
      }
    }

    throw new Error(
      `Bedrock 回應無法通過 ${outputSchema.name} 的語意驗證（${this.description}，已嘗試 ${this.maxAttempts} 次）：` +
        formatValidationError(lastError),
    );
  }

  private buildRequest(
    system: string,
    messages: Message[],
    outputSchema: OutputSchemaSpec,
  ): ConverseCommandInput {
    const request: ConverseCommandInput = {
      modelId: this.modelId,
      system: [{ text: system }],
      messages,
      inferenceConfig: { maxTokens: this.maxTokens, temperature: this.temperature },
    };
    if (this.useStructuredOutputs) {
      request.outputConfig = {
        textFormat: {
          type: 'json_schema',
          structure: {
            jsonSchema: {
              name: outputSchema.name,
              description: outputSchema.description,
              // Bedrock 要求這裡是 JSON 字串，不是物件。
              schema: outputSchema.json,
            },
          },
        },
      };
    }
    return request;
  }
}

/**
 * bearer 認證要把 token 交給 SDK，並把 httpBearerAuth 排到 sigv4 前面 ——
 * Bedrock client 預設的 auth scheme 順序是 sigv4 優先，不調整的話有 sigv4 憑證時
 * bearer token 根本不會被用到。
 */
function buildRuntimeClient(
  options: BedrockRuntimeAdapterOptions,
  authMode: BedrockAuthMode,
): BedrockRuntimeClient {
  if (authMode === 'bearer' && options.apiKey) {
    return new BedrockRuntimeClient({
      region: options.region,
      token: { token: options.apiKey },
      authSchemePreference: ['httpBearerAuth'],
    });
  }
  return new BedrockRuntimeClient({ region: options.region });
}

/**
 * 依環境變數決定用真的 Bedrock 還是 Mock。
 *
 * 找不到模型或 region 時自動退回 `MockBedrockClient`，所以同一份程式碼在沒有 AWS
 * 權限的機器上也跑得起來，設好環境變數後呼叫端（`src/handlers/*.ts`）一行都不用改。
 *
 * 變數名的別名處理（`MODEL_NAMME`、`CLAUDE_KEY` 等）集中在 `resolveBedrockEnv()`。
 */
export function createBedrockClientFromEnv(env: NodeJS.ProcessEnv = process.env): BedrockClient {
  const config = resolveBedrockEnv(env);
  if (config.modelId === null || config.region === null) {
    return new MockBedrockClient();
  }
  return new BedrockRuntimeAdapter({
    modelId: config.modelId,
    region: config.region,
    apiKey: config.apiKey,
    authMode: config.authMode,
    maxTokens: parsePositiveInt(env.BEDROCK_MAX_TOKENS),
    temperature: parseTemperature(env.BEDROCK_TEMPERATURE),
    // 逃生門：如果選到的 model 不支援原生 structured outputs（會回 400），
    // 設 BEDROCK_STRUCTURED_OUTPUT=off 就改成只靠 prompt 要求 JSON。
    useStructuredOutputs: env.BEDROCK_STRUCTURED_OUTPUT !== 'off',
    maxAttempts: parsePositiveInt(env.BEDROCK_MAX_ATTEMPTS),
  });
}

/** Converse 回應可能拆成多個 text block，全部串起來再剖析。 */
function extractResponseText(content: ContentBlock[] | undefined): string | null {
  if (!content) {
    return null;
  }
  const text = content
    .map((block) => ('text' in block && typeof block.text === 'string' ? block.text : ''))
    .join('')
    .trim();
  return text.length > 0 ? text : null;
}

/**
 * 剖析模型回傳的 JSON。
 *
 * 開了 structured outputs 的話理論上會是乾淨 JSON，但這裡仍然容錯處理 markdown
 * code fence 與前後多餘文字 —— 因為 `BEDROCK_STRUCTURED_OUTPUT=off` 的逃生門
 * 走的就是沒有保證的路徑，兩條路徑共用同一個剖析器才不會只有一條被測到。
 */
export function parseJsonPayload(text: string): unknown {
  const fenced = text.match(/```(?:json)?\s*([\s\S]*?)```/);
  const candidate = (fenced ? fenced[1] : text).trim();
  try {
    return JSON.parse(candidate);
  } catch {
    const start = candidate.indexOf('{');
    const end = candidate.lastIndexOf('}');
    if (start === -1 || end <= start) {
      throw new Error(`模型回應不是有效的 JSON，也找不到可剖析的物件片段：${truncate(candidate, 300)}`);
    }
    return JSON.parse(candidate.slice(start, end + 1));
  }
}

function buildRepairInstruction(error: unknown): string {
  return [
    '你上一個回答沒有通過 schema 驗證，請只修正下列問題，其他內容盡量保留：',
    formatValidationError(error),
    '請重新輸出**完整**的 JSON 物件（不是差異），且不要加任何 JSON 以外的文字或 markdown code fence。',
  ].join('\n');
}

function formatValidationError(error: unknown): string {
  if (error instanceof z.ZodError) {
    return error.issues.map((issue) => `- ${issue.path.join('.') || '(root)'}: ${issue.message}`).join('\n');
  }
  return error instanceof Error ? error.message : String(error);
}

function extractEvidenceIds(userPrompt: string): string[] {
  return [...userPrompt.matchAll(/evidenceId="([^"]+)"/g)].map((match) => match[1]);
}

function extractFindingIds(userPrompt: string): string[] {
  return [...userPrompt.matchAll(/findingId="([^"]+)"/g)].map((match) => match[1]);
}

/**
 * Mock 也要把 context 傳來的既知限制帶出來，否則「資料不足會誠實標示」這件事測不到。
 *
 * 標題用 `KNOWN_LIMITATIONS_HEADER` 常數而不是自己寫一份一樣的中文字串 ——
 * 原本兩邊各寫一份，還得靠一個測試提醒「改了要一起改」，而我改 prompt 的時候
 * 果然就踩到了。
 */
function extractKnownLimitations(userPrompt: string): string[] {
  const header = KNOWN_LIMITATIONS_HEADER.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const section = userPrompt.match(new RegExp(`${header}\\n([\\s\\S]*?)(?:\\n\\n|$)`));
  if (!section) {
    return [];
  }
  return section[1]
    .split('\n')
    .map((line) => line.replace(/^-\s*/, '').trim())
    .filter((line) => line.length > 0);
}

function parsePositiveInt(value: string | undefined): number | undefined {
  if (value === undefined) {
    return undefined;
  }
  const parsed = Number.parseInt(value, 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : undefined;
}

function parseTemperature(value: string | undefined): number | undefined {
  if (value === undefined) {
    return undefined;
  }
  const parsed = Number.parseFloat(value);
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : undefined;
}

function truncate(value: string, max: number): string {
  return value.length <= max ? value : `${value.slice(0, max)}…`;
}
