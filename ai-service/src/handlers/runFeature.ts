import type { BedrockClient } from '../bedrock/client.js';
import type { PromptPayload } from '../prompts/promptPayload.js';
import { AiRequestContextSchema, type AiContext, type AiRequestContext } from '../types/aiEvidence.js';
import {
  findUnknownEvidenceIds,
  findUnknownFindingIds,
  type StructuredOutput,
} from '../types/structuredOutput.js';
import {
  collectSourceAttributions,
  collectWebSourceAttributions,
  type SourceAttribution,
} from '../types/sourceAttribution.js';
import type { WebFinding } from '../types/webFinding.js';
import {
  DisabledWebSearchProvider,
  MAX_WEB_FINDINGS,
  type WebSearchProvider,
} from '../websearch/provider.js';
import { buildEvidenceInventory } from './evidenceInventory.js';
import { buildInsufficientDataOutput, shouldReportInsufficientData } from './insufficientData.js';

/**
 * 一個功能的完整結果。
 *
 * `output` 與 `sources` 綁在同一個回傳值裡是刻意的：需求是「每個回應都要附資料來源」，
 * 如果來源是另一個要自己記得呼叫的函式，總有一天會有人忘記，而忘記的後果是輸出
 * 看起來很完整但無法查證。綁在一起就不可能拿到分析而沒拿到來源。
 */
export interface AiFeatureResult {
  output: StructuredOutput;
  /**
   * 資料來源，由程式從**實際被 basis 引用的 evidence** 推導，不是模型產生的。
   * 模型碰不到這個欄位，所以不可能出現捏造的機關名稱或網址。
   */
  sources: SourceAttribution[];
}

/**
 * 三個功能共用的執行流程。抽出來的原因不是省行數，是因為下面每一個步驟
 * （空資料短路、evidenceId 驗證、限制回填、來源推導）**漏掉任何一個都會產生
 * 不誠實的輸出**，而三個 handler 各寫一份就一定會有人漏。
 */
export async function runFeature(
  client: BedrockClient,
  request: AiRequestContext,
  buildPrompt: (context: AiContext) => PromptPayload,
  webSearch: WebSearchProvider = new DisabledWebSearchProvider(),
): Promise<AiFeatureResult> {
  const validated = AiRequestContextSchema.parse(request);

  // 1. 使用者開啟上網搜尋時就去搜 —— **不管管線有沒有資料。**
  //
  //    順序很重要：搜尋必須排在「資料不足」判斷之前。使用者明確按了那顆開關，
  //    卻因為 DB 沒資料就不搜，那個開關等於騙人。管線沒資料正是最需要上網的時候。
  //
  //    搜尋失敗絕不讓整個請求失敗——它是加分功能，掛掉就照原本的資料回答。
  const { findings, notes } = await resolveWebFindings(validated, webSearch);

  // 2. 兩邊都沒有資料才是真的「資料不足」，這時不呼叫模型。
  //    只有 webFindings 沒有 evidence 是允許的（純網路回答），
  //    但 schema 會強制在 limitations 說明「沒有官方統計支撐」。
  if (shouldReportInsufficientData(validated.evidence.length, findings.length)) {
    return {
      output: buildInsufficientDataOutput(
        [...validated.knownLimitations, ...notes].length > 0
          ? [...validated.knownLimitations, ...notes]
          : ['本次請求沒有任何可引用的資料，因此無法產生有依據的分析。'],
      ),
      sources: [],
    };
  }

  const context: AiContext = {
    ...validated,
    evidence: validated.evidence,
    webFindings: findings,
    knownLimitations: [...validated.knownLimitations, ...notes],
  };
  const raw = await client.invokeStructured(buildPrompt(context));

  // 3. 擋掉捏造的引用。schema 看不到 context，所以只能在這裡驗。
  //    這一步也是來源推導的前提：ID 對不上，來源就無從追溯。
  const unknownEvidence = findUnknownEvidenceIds(
    raw,
    context.evidence.map((item) => item.evidenceId),
  );
  if (unknownEvidence.length > 0) {
    throw new Error(
      `模型引用了不存在的 evidenceId：${unknownEvidence.join(', ')}。` +
        '這代表輸出的判斷依據無法追溯到真實資料，已拒絕回傳。',
    );
  }

  const unknownFindings = findUnknownFindingIds(
    raw,
    context.webFindings.map((finding) => finding.findingId),
  );
  if (unknownFindings.length > 0) {
    throw new Error(
      `模型引用了不存在的網路來源 findingId：${unknownFindings.join(', ')}。` +
        '這通常代表模型憑記憶編了一個網址，已拒絕回傳。',
    );
  }

  // 4. context builder 確定知道的限制一定要出現在輸出裡。
  //    這一步從「補模型漏抄的」變成「唯一的來源」：模型現在被明確要求**不要**抄寫
  //    既知限制（實測那佔了 25% 的輸出），所以這裡附加的就是完整的既知限制。
  //    模型自己新增的限制會保留在前面。
  const withLimitations = withKnownLimitations(raw, context.knownLimitations);

  // 5. 用程式盤點的 evidence 清單覆蓋 evidenceReview 的三個列舉欄位。
  //    模型只產出 missingForQuestion（那是唯一需要判斷的），其餘由程式算 ——
  //    既省掉 35% 的輸出，盤點結果也比模型寫的更可靠（不會列錯或漏列）。
  const output: StructuredOutput = {
    ...withLimitations,
    evidenceReview: buildEvidenceInventory(
      context.evidence,
      withLimitations.evidenceReview.missingForQuestion,
    ),
  };

  // 6. 從實際被引用的 evidence 與網路來源推導資料來源清單。
  return {
    output,
    sources: [
      ...collectSourceAttributions(context.evidence, output),
      ...collectWebSourceAttributions(context.webFindings, output),
    ],
  };
}

/**
 * 執行網路搜尋（如果使用者開啟了）。
 *
 * 搜尋 query 用使用者的問題原文。刻意不讓模型自己決定要搜什麼：
 * 那需要多一輪 tool-use 往返，而延遲已經是這個服務最大的風險
 * （單次 15–21 秒，API Gateway 上限 29/30 秒）。
 */
async function resolveWebFindings(
  request: AiRequestContext,
  provider: WebSearchProvider,
): Promise<{ findings: WebFinding[]; notes: string[] }> {
  if (!request.webSearch.enabled) {
    // 呼叫端可以直接塞 webFindings（測試與未來的預先檢索會用到）。
    return { findings: request.webFindings, notes: [] };
  }

  const query = buildSearchQuery(request);
  if (query.trim().length === 0) {
    return {
      findings: [],
      notes: ['已開啟上網搜尋，但這次請求沒有可用的搜尋主題，因此未執行搜尋。'],
    };
  }

  try {
    const result = await provider.search(query, request.webSearch);
    const findings = result.findings.slice(0, MAX_WEB_FINDINGS);
    const notes = [...result.notes];
    if (findings.length === 0) {
      notes.push('已開啟上網搜尋，但沒有找到相關的網路資料，本次回應僅使用資料管線的資料。');
    } else {
      notes.push(
        `已開啟上網搜尋，本次取得 ${findings.length} 筆網路資料。` +
          '這些內容不是資料管線的官方統計，未經驗證，可信度低於其他 evidence。',
      );
    }
    return { findings, notes };
  } catch (error) {
    // 搜尋壞掉不該讓使用者拿到 502。誠實說搜尋失敗，然後照原本的資料回答。
    return {
      findings: [],
      notes: [
        '已開啟上網搜尋，但搜尋失敗，本次回應僅使用資料管線的資料' +
          `（原因：${error instanceof Error ? error.message : String(error)}）。`,
      ],
    };
  }
}

/**
 * 組搜尋用的 query。
 *
 * ## 為什麼不能直接用使用者的問題原文
 *
 * 實測踩到的：使用者問「為何八里薪資第六高？」，直接拿這句去搜，Tavily 回來的是
 * **雲林與台中**薪資比較的 Threads 討論 —— 因為那句話裡沒有任何地理脈絡，
 * 「八里」單獨看也可能是別的地方。模型很誠實地標了「未經驗證」，
 * 但拿一則講雲林的社群貼文當新北八里的背景，對青年局來說是沒有價值的來源。
 *
 * 對照組：同一批測試裡「為何坪林薪資是全新北最高？」因為問句本身含「全新北」，
 * 搜到的是水利署的坪林專題報導 —— 差別只在 query 有沒有地理脈絡。
 *
 * 所以這裡把「新北市」與行政區名補上。已經出現在問題裡的就不重複加，
 * 避免 query 變成「新北市 八里區 為何八里薪資…」這種權重被稀釋的字串。
 */
export function buildSearchQuery(request: AiRequestContext): string {
  const question = request.question?.trim() ?? '';
  if (question.length === 0) {
    // 沒有 question 時（Data Explanation / Policy Copilot）用情境組一個主題。
    return ['新北市', request.focusDistrict, request.focusArea, '青年 政策']
      .filter((part): part is string => Boolean(part))
      .join(' ');
  }

  const contextParts = ['新北市', request.focusDistrict]
    .filter((part): part is string => Boolean(part))
    // 「新北市」已經在問句裡（例如「全新北」）就不再加；行政區名同理。
    .filter((part) => !question.includes(part) && !question.includes(part.replace(/[市區]$/, '')));

  return [question, ...contextParts].join(' ');
}

/**
 * 把既知限制補回輸出。用「包含子字串」而不是完全相等來判斷是否已存在，
 * 因為模型常會把限制改寫成自己的句子；那種情況不需要重複列一次。
 */
export function withKnownLimitations(
  output: StructuredOutput,
  knownLimitations: readonly string[],
): StructuredOutput {
  const missing = knownLimitations.filter(
    (note) => !output.limitations.some((existing) => existing.includes(note) || note.includes(existing)),
  );
  if (missing.length === 0) {
    return output;
  }
  return { ...output, limitations: [...output.limitations, ...missing] };
}
