import type { BedrockClient } from '../bedrock/client.js';
import type { AiRequestContext } from '../types/aiEvidence.js';
import { buildDataExplanationPrompt } from '../prompts/dataExplanation.js';
import type { WebSearchProvider } from '../websearch/provider.js';
import { runFeature, type AiFeatureResult } from './runFeature.js';

/**
 * Dashboard Data Explanation：把已算好的統計資料解釋成使用者看得懂的文字。
 * 回傳值同時帶 `output` 與 `sources`，來源不可能被漏掉。
 */
export async function explainData(
  client: BedrockClient,
  context: AiRequestContext,
  webSearch?: WebSearchProvider,
): Promise<AiFeatureResult> {
  return runFeature(client, context, buildDataExplanationPrompt, webSearch);
}
