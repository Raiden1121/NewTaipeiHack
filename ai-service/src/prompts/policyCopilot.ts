import type { AiContext } from '../types/aiEvidence.js';
import { AI_GUARDRAILS, buildUserPrompt } from './guardrails.js';
import { REASONING_PROCEDURE, UNIT_HANDLING_RULES } from './reasoningProcedure.js';
import { formatFewShotExample } from './fewShotExample.js';
import type { PromptPayload } from './promptPayload.js';

/**
 * AI Policy Copilot：整理問題辨識、發展優勢、資源缺口、政策方向、判斷依據與資料限制。
 * 對應 README「AI Policy Copilot」與 `ai-service.md` 的 AI Policy Copilot 責任。
 *
 * ⚠️ 這個功能的範圍受決策 A 影響：`data-pipeline` 的 Deterministic Analytics
 * （Opportunity Index、Retention Risk、資源缺口等複合指標）還沒產出，所以目前
 * 「跨指標綜合判斷」只能建立在原始指標上。system prompt 因此明確要求模型
 * 在缺少彙總指標時說出來，而不是硬做出一個綜合結論。
 */
export function buildPolicyCopilotPrompt(context: AiContext): PromptPayload {
  const system = [
    '你是新北市青年局的政策分析輔助角色。',
    '任務：根據已計算好的青年發展指標，整理出問題辨識、發展優勢、資源缺口與可能的政策方向，協助青年局同仁快速掌握狀況、找出青年需求與資源供給之間的落差。',
    REASONING_PROCEDURE,
    [
      '額外要求（Policy Copilot 專屬，這些細化上面的思考程序）：',
      '- 目前資料管線的複合指標（Opportunity Index、Retention Risk、資源缺口分數等）尚未產出，你只會拿到原始指標。',
      '- 因此**不要**自己組出一個綜合分數或排名來代替那些指標。第 1 步盤點時就要把缺少的彙總指標寫進 missingForQuestion，所以 Policy Copilot 目前幾乎不可能是 sufficient。',
      '- policyDirections 要寫成「可考慮的方向」而不是「應該執行的決定」，並且每個方向都要指得出是哪一筆 evidence 讓你這樣建議。',
      '- 資源供給側（青年局預算、職訓課程、托育量能）與需求側（青年人口、職缺）的資料粒度常常不一致，不可直接相除或相減當成缺口數字。',
      '- 「資源缺口」在沒有彙總指標之前，只能描述成「兩側資料粒度不對等，無法量化落差」，不可以自己估一個數字或比例。',
    ].join('\n'),
    AI_GUARDRAILS,
    UNIT_HANDLING_RULES,
    formatFewShotExample(),
  ].join('\n\n');

  const user = buildUserPrompt(context, [
    context.focusDistrict ? `分析範圍：${context.focusDistrict}` : '分析範圍：全市（citywide，跨區比較）',
    context.focusArea ? `關注主題：${context.focusArea}` : null,
    context.question
      ? `使用者的具體問題：${context.question}`
      : '使用者沒有指定具體問題，請針對下方 evidence 做整體政策分析。',
  ]);

  return { system, user };
}
