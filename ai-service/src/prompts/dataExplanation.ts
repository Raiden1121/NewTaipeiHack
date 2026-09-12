import type { AiContext } from '../types/aiEvidence.js';
import { AI_GUARDRAILS, buildUserPrompt } from './guardrails.js';
import { REASONING_PROCEDURE, UNIT_HANDLING_RULES } from './reasoningProcedure.js';
import { formatFewShotExample } from './fewShotExample.js';
import type { PromptPayload } from './promptPayload.js';

export type { PromptPayload } from './promptPayload.js';

/**
 * Dashboard Data Explanation：把已算好的統計資料解釋成一般使用者容易理解的文字。
 * 對應 README「Data Explanation」與 `ai-service.md` 的 Dashboard Data Explanation 責任。
 *
 * system prompt 的組裝順序固定為：角色 → 任務 → 思考程序 → 邊界規則 → 單位規則 → 範例。
 * 先給程序再給禁止事項，是因為單有禁止事項時模型仍然可以「先寫結論再湊依據」。
 */
export function buildDataExplanationPrompt(context: AiContext): PromptPayload {
  const system = [
    '你是新北青年 Dashboard 的資料解說助理。',
    '任務：把已經算好的青年相關統計資料（人口、職缺、薪資、居住、交通、青年局資源等）解釋成一般使用者容易理解的文字。對象是不熟統計的一般市民與青年局同仁，請避免術語堆疊。',
    REASONING_PROCEDURE,
    AI_GUARDRAILS,
    UNIT_HANDLING_RULES,
    formatFewShotExample(),
  ].join('\n\n');

  const user = buildUserPrompt(context, [
    context.focusDistrict
      ? `使用者目前查看的行政區：${context.focusDistrict}`
      : '使用者目前查看：全市（citywide）',
    context.focusArea ? `使用者目前查看的主題：${context.focusArea}` : null,
    context.question
      ? `使用者問題：${context.question}`
      : '使用者沒有特定問題，請直接解釋以下資料呈現的意義。',
  ]);

  return { system, user };
}
