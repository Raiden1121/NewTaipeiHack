import {
  QA_OUTPUT_SCHEMA_DESCRIPTION,
  QA_OUTPUT_SCHEMA_NAME,
  STRUCTURED_OUTPUT_SCHEMA_DESCRIPTION,
  STRUCTURED_OUTPUT_SCHEMA_NAME,
  qaOutputSchemaJson,
  structuredOutputSchemaJson,
} from '../types/structuredOutputJsonSchema.js';
import {
  QaOutputSchema,
  StructuredOutputSchema,
  type StructuredOutput,
} from '../types/structuredOutput.js';

/**
 * 一種輸出格式的完整規格：Bedrock 用的 JSON Schema ＋ 語意驗證用的 zod schema。
 *
 * 兩個必須綁在一起傳，因為它們是同一件事的兩個面向（形狀 vs 語意），
 * 分開傳很容易出現「JSON Schema 換了但 zod 沒換」這種對不起來的狀態。
 */
export interface OutputSchemaSpec {
  name: string;
  description: string;
  /** Bedrock `outputConfig` 要的 JSON 字串 */
  json: string;
  /**
   * 語意驗證。回傳型別統一是 `StructuredOutput`，因為兩種格式共用同一個物件
   * （Q&A 只是多填 `answer`、四塊留空），所以下游的 handler / 來源推導都不用分岔。
   */
  parse: (value: unknown) => StructuredOutput;
}

/**
 * 參數型別刻意只要求「有 parse 方法」而不是 `z.ZodType<StructuredOutput>`。
 *
 * 原因是這兩個 schema 有 `.default()`，zod 的輸入型別（欄位可省略）跟輸出型別
 * （欄位必填）不一樣，所以它們不符合 `ZodType<StructuredOutput>`。
 * 這裡真正在意的只有「parse 之後拿到的是 StructuredOutput」。
 */
function toSpec(
  name: string,
  description: string,
  json: string,
  schema: { parse: (value: unknown) => StructuredOutput },
): OutputSchemaSpec {
  return { name, description, json, parse: (value) => schema.parse(value) };
}

/** 六塊格式：Dashboard Data Explanation 與 AI Policy Copilot。 */
export const SIX_BLOCK_OUTPUT_SPEC: OutputSchemaSpec = toSpec(
  STRUCTURED_OUTPUT_SCHEMA_NAME,
  STRUCTURED_OUTPUT_SCHEMA_DESCRIPTION,
  structuredOutputSchemaJson(),
  StructuredOutputSchema,
);

/** Q&A 格式：`answer` 為主，四塊分析只在政策類問題才填。 */
export const QA_OUTPUT_SPEC: OutputSchemaSpec = toSpec(
  QA_OUTPUT_SCHEMA_NAME,
  QA_OUTPUT_SCHEMA_DESCRIPTION,
  qaOutputSchemaJson(),
  QaOutputSchema,
);

/**
 * 送進模型的 prompt。刻意拆成 system / user 兩段，對應 Bedrock Converse API 的
 * `system` 與 `messages`：規則與範例放 system，這次請求的實際資料放 user。
 *
 * 這麼分不只是形式：system 內容在同一個 session 內是固定的，之後要接 prompt caching
 * 時可以直接快取這一段。
 */
export interface PromptPayload {
  system: string;
  user: string;
  /**
   * 這次要用哪一種輸出格式。省略時是六塊。
   *
   * 放在 payload 裡而不是當 `invokeStructured()` 的另一個參數，是因為 prompt 的內容
   * 與它要求的輸出格式是同一個決定 —— 例如 Q&A 的 prompt 會叫模型「直接回答」，
   * 那就必須搭配有 `answer` 欄位的 schema。分成兩個參數傳，遲早會有人只改一邊。
   */
  outputSchema?: OutputSchemaSpec;
}
