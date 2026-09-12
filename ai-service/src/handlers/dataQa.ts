import type { BedrockClient } from '../bedrock/client.js';
import type { AiRequestContext } from '../types/aiEvidence.js';
import { buildDataQaPrompt } from '../prompts/dataQa.js';
import type { WebSearchProvider } from '../websearch/provider.js';
import { runFeature, type AiFeatureResult } from './runFeature.js';

/**
 * AI Data Q&A：回答使用者對 29 區資料的比較與查詢。需要 context.question。
 *
 * 注意 question 的檢查刻意放在 `buildDataQaPrompt`（也就是「資料不足短路」之後）：
 * 沒有 evidence 是資料問題，要誠實回答；沒有 question 是呼叫端的程式錯誤，該丟錯。
 * 兩者不該混在一起處理。
 */
export async function dataQa(
  client: BedrockClient,
  context: AiRequestContext,
  webSearch?: WebSearchProvider,
): Promise<AiFeatureResult> {
  return runFeature(client, context, buildDataQaPrompt, webSearch);
}
