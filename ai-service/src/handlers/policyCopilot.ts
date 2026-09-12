import type { BedrockClient } from '../bedrock/client.js';
import type { AiRequestContext } from '../types/aiEvidence.js';
import { buildPolicyCopilotPrompt } from '../prompts/policyCopilot.js';
import type { WebSearchProvider } from '../websearch/provider.js';
import { runFeature, type AiFeatureResult } from './runFeature.js';

/** AI Policy Copilot：問題辨識、發展優勢、資源缺口、政策方向、判斷依據、資料限制。 */
export async function policyCopilot(
  client: BedrockClient,
  context: AiRequestContext,
  webSearch?: WebSearchProvider,
): Promise<AiFeatureResult> {
  return runFeature(client, context, buildPolicyCopilotPrompt, webSearch);
}
