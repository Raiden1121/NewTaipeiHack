import type { AiContext } from '../types/aiEvidence.js';
import { AI_GUARDRAILS, buildUserPrompt } from './guardrails.js';
import { REASONING_PROCEDURE, UNIT_HANDLING_RULES } from './reasoningProcedure.js';
import { formatFewShotExample } from './fewShotExample.js';
import type { PromptPayload } from './promptPayload.js';

/**
 * AI Data Q&A：回答使用者對 29 區資料的比較與查詢。
 * 對應 README「AI Data Q&A」與 `ai-service.md` 的 AI Data Q&A 責任。
 */
export function buildDataQaPrompt(context: AiContext): PromptPayload {
  if (!context.question) {
    throw new Error('buildDataQaPrompt 需要 context.question（Q&A 情境一定要有使用者問題）');
  }

  const system = [
    '你是新北青年 Dashboard 的資料問答助理。',
    '任務：根據已經算好的 29 區青年相關資料，回答使用者的比較與查詢問題。',
    REASONING_PROCEDURE,
    [
      '額外要求（Q&A 專屬，這些細化上面的思考程序）：',
      '- 第 1 步盤點時，missingForQuestion 要具體寫出「使用者問了什麼、但 evidence 裡沒有」。Q&A 是三個功能裡最容易被問到沒有資料的東西的。',
      '- 如果使用者問的是比較（哪一區最高／最低），只能比較 evidence 裡真的有的區。沒有資料的區要在 limitations 明確列出來，不可跳過不提 —— 少了幾區的排名是誤導。',
      '- 如果使用者問的東西 evidence 完全沒有涵蓋，就是 insufficient：直接說明無法回答，不可用相近的資料勉強代答（例如問薪資卻拿職缺數回答）。',
      '- **直接比大小（誰多誰少、誰最高）是允許的**，那是讀值不是計算。',
      '- 但算差值（A 比 B 多幾人）、比例（多幾成）、成長率都**不允許**，那些要等 analytics 產出。',
      '  真的被問到差值時，只列出兩邊的原始數值，並說明「差值需由資料管線計算，此處僅提供原始數字」。',
    ].join('\n'),
    AI_GUARDRAILS,
    UNIT_HANDLING_RULES,
    formatFewShotExample(),
  ].join('\n\n');

  const user = buildUserPrompt(context, [
    `使用者問題：${context.question}`,
    context.focusDistrict ? `使用者目前查看的行政區：${context.focusDistrict}` : null,
    context.focusArea ? `使用者目前查看的主題：${context.focusArea}` : null,
  ]);

  return { system, user };
}
