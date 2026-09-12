import { z } from 'zod';

export const DISCLAIMER_KEYWORD = '不代表政府正式政策決定';

export const BasisCitationSchema = z.object({
  evidenceId: z.string().min(1).describe('必須是這次 context 裡真的存在的 evidenceId，不可發明'),
  note: z.string().nullable().describe('這筆 evidence 如何支持前面的判斷'),
});
export type BasisCitation = z.infer<typeof BasisCitationSchema>;

/** 網路來源的引用。跟 `BasisCitationSchema` 分開，因為可信度層級不同。 */
export const WebReferenceSchema = z.object({
  findingId: z.string().min(1).describe('必須是這次 context 的 webFindings 裡真的存在的 findingId'),
  note: z.string().nullable().describe('這筆網路資料補充了什麼；必須寫成「根據網路資料…」的語氣'),
});
export type WebReference = z.infer<typeof WebReferenceSchema>;

/**
 * 這次回應的資料充足程度。
 *
 * 為什麼要獨立成一個欄位，而不是讓前端去猜 limitations 的內容：
 * `ai-service.md` 要求「資料不足時必須標示限制，不能硬答」。如果「資料不足」只是
 * limitations 陣列裡的一句中文，前端沒辦法可靠地判斷要不要換一種呈現方式
 * （例如顯示「目前無法回答」而不是把空的分析結果畫成卡片）。
 *
 * - `sufficient`：evidence 足以回答，結論有依據
 * - `partial`：部分面向有資料、部分缺漏，結論只在有資料的範圍內成立
 * - `insufficient`：沒有足夠 evidence，**不應該給出實質結論**
 */
export const DataSufficiencySchema = z.enum(['sufficient', 'partial', 'insufficient']);
export type DataSufficiency = z.infer<typeof DataSufficiencySchema>;

/**
 * 思考程序第 1 步的產物：對這次 evidence 的盤點。
 *
 * 為什麼要當成必須輸出的欄位，而不是讓模型心裡想想：
 * 1. **有輸出才驗得到。** 下面的 superRefine 可以檢查盤點結果與 `dataSufficiency`
 *    是否自相矛盾（說缺資料卻又宣稱 sufficient）。
 * 2. **順序效果。** 這個欄位在 schema 裡排第一，而 JSON 是依欄位順序生成的，
 *    所以模型會先盤點才寫結論，而不是先寫結論再回頭湊 basis。
 * 3. **稽核。** 出問題時分得出來是「資料判讀錯」還是「有資料但推論錯」。
 *
 * 前端可以預設收起這一塊，它主要是給人查證與除錯用的。
 */
export const EvidenceReviewSchema = z.object({
  /**
   * 下面三個欄位**由程式盤點，模型不需要輸出**（見 `handlers/evidenceInventory.ts`）。
   *
   * 所以它們是 `.default([])`：模型的原始回應裡不會有這幾個 key，
   * `runFeature()` 會在驗證通過後填入程式算好的內容。
   *
   * 為什麼要改：實測模型花了整體輸出的 35% 在重打這三份清單，而內容完全來自
   * `context.evidence`，沒有任何判斷成分 —— 而延遲是被輸出量決定的。
   * 程式算的版本還更可靠，不會列錯或漏列。
   */
  availableMetrics: z
    .array(z.string())
    .default([])
    .describe('這次拿到哪些指標，格式「metricId（範圍／期間）」。由程式盤點。'),
  youthSpecificMetrics: z
    .array(z.string())
    .default([])
    .describe('youthEligibility=eligible 的指標，只有這些能當青年專屬數據解讀。由程式盤點。'),
  contextOnlyMetrics: z
    .array(z.string())
    .default([])
    .describe('youthEligibility=context_only 或 proxy_only 的指標，只能當整體脈絡。由程式盤點。'),
  /**
   * 這一個仍然由模型輸出，因為它是唯一需要判斷的：
   * 「要回答眼前這個問題還缺什麼」取決於問題本身，程式無從得知。
   * 下面的 superRefine 也主要綁在這個欄位上。
   */
  missingForQuestion: z
    .array(z.string())
    .describe('要回答眼前的問題還缺哪些資料；沒有缺就是空陣列'),
});
export type EvidenceReview = z.infer<typeof EvidenceReviewSchema>;

/**
 * 六塊 structured output，對應 `ai-service/ai-service.md` 與 README 的規則：
 * 問題辨識 / 發展優勢 / 資源缺口 / 政策方向 / 判斷依據 / 資料限制。
 *
 * 加上兩個支撐欄位：`evidenceReview`（思考過程）與 `dataSufficiency`（充足度）。
 *
 * 設計原則：
 * - issues / strengths / resourceGaps / policyDirections 都允許空陣列（某個面向真的
 *   沒有發現），但欄位本身不可省略。
 * - 欄位順序有意義：`evidenceReview` → `dataSufficiency` → 四塊結論 → basis。
 *   這就是要模型走的思考順序。
 * - disclaimer 用 refine 檢查關鍵字而不是要求逐字一致，因為模型措辭會有差異；
 *   但一定要包含「不代表政府正式政策決定」。
 */
export const StructuredOutputSchema = z
  .object({
    evidenceReview: EvidenceReviewSchema,
    dataSufficiency: DataSufficiencySchema,
    issues: z.array(z.string()).describe('問題辨識'),
    strengths: z.array(z.string()).describe('發展優勢'),
    resourceGaps: z.array(z.string()).describe('資源缺口'),
    policyDirections: z.array(z.string()).describe('政策方向'),
    basis: z
      .array(BasisCitationSchema)
      .describe('判斷依據，只能引用資料管線的 evidenceId，不可放網路來源'),
    /**
     * 網路搜尋來源的引用。**跟 basis 是分開的陣列。**
     *
     * 為什麼不共用 basis：basis 代表「這個判斷有資料管線的數字支撐」，那是可追溯
     * 可重現的。網路內容不是。如果兩者混在同一個陣列，前端就沒辦法區分
     * 「這句話有官方統計支撐」和「這句話是某個網頁說的」—— 而使用者是青年局，
     * 他們拿這個做政策判斷。
     *
     * 分開之後還有一個結構性好處：`basis` 不可為空的規則仍然成立，
     * 所以模型不可能只靠網路資料就寫出結論。
     */
    webReferences: z
      .array(WebReferenceSchema)
      .default([])
      .describe('網路來源引用；沒有使用網路資料時為空陣列'),
    limitations: z
      .array(z.string())
      .describe('資料限制；沒有限制時仍要回傳空陣列 []，不可省略這個欄位'),
    disclaimer: z.string().refine((value) => value.includes(DISCLAIMER_KEYWORD), {
      message: `disclaimer 必須包含「${DISCLAIMER_KEYWORD}」字樣`,
    }),
  })
  .superRefine((output, ctx) => {
    const hasConclusions =
      output.issues.length > 0 ||
      output.strengths.length > 0 ||
      output.resourceGaps.length > 0 ||
      output.policyDirections.length > 0;

    // 有結論就必須有依據。這是整個 schema 最核心的一條規則。
    //
    // 「依據」可以是資料管線的 evidence（basis）或網路來源（webReferences）：
    // 使用者明確開啟上網搜尋、而管線又沒有資料時，純網路的回答是合理的產出。
    // 但**完全沒有任何引用**的結論一律不接受 —— 那就是憑空編造。
    const hasAnyCitation = output.basis.length > 0 || output.webReferences.length > 0;
    if (hasConclusions && !hasAnyCitation) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['basis'],
        message:
          'issues / strengths / resourceGaps / policyDirections 只要有任何一條內容，basis 或 webReferences 至少要有一筆：每個論點都必須有可追溯的依據。',
      });
    }

    // 純網路回答（沒有任何管線 evidence）必須在 limitations 說清楚。
    //
    // 這是放寬上面那條規則之後最重要的補償機制：使用者看到一份分析時，
    // 必須能知道「這完全沒有官方統計支撐」，否則純網路的內容會被當成
    // 資料管線的分析結果 —— 而使用者是青年局，他們拿這個做政策判斷。
    if (hasConclusions && output.basis.length === 0 && output.webReferences.length > 0) {
      const declaresWebOnly = output.limitations.some(
        (note) => note.includes('沒有') && note.includes('網路'),
      );
      if (!declaresWebOnly) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          path: ['limitations'],
          message:
            '這份回答完全沒有資料管線的 evidence（basis 為空），只有網路來源。limitations 必須明確說明「本次沒有資料管線的官方統計，以下內容僅來自網路搜尋」。',
        });
      }
    }

    // 標示資料不足，就不該同時給出實質結論——那是自相矛盾。
    if (output.dataSufficiency === 'insufficient' && hasConclusions) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['dataSufficiency'],
        message:
          'dataSufficiency 為 insufficient 時不可給出實質結論（issues / strengths / resourceGaps / policyDirections 都必須為空），資料不足就只說明限制。',
      });
    }

    // 說資料不足，卻沒說缺什麼，等於沒有交代。
    //
    // 接受 limitations 或 missingForQuestion 任一非空 —— 兩者都是模型產出的，
    // 所以這條規則仍然約束得到模型。
    //
    // 為什麼不只看 limitations：模型現在**不需要**把 context 的既知限制抄進
    // limitations（那些由 `withKnownLimitations()` 自動附加），所以在「既知限制已經
    // 說明了缺什麼、模型沒有額外要補的」這種正常情況下，模型的 limitations 會是空的。
    // 只看 limitations 會把這種合法輸出誤判成違規。
    if (
      output.dataSufficiency !== 'sufficient' &&
      output.limitations.length === 0 &&
      output.evidenceReview.missingForQuestion.length === 0
    ) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['limitations'],
        message:
          'dataSufficiency 不是 sufficient 時，必須說明缺了什麼：' +
          'limitations 或 evidenceReview.missingForQuestion 至少要有一項非空。',
      });
    }

    // ---- 以下三條把「盤點結果」與「充足度判斷」綁在一起 ----
    // 這是 evidenceReview 存在的主要價值：讓充足度判斷變成可檢查的，
    // 而不是模型隨口給一個標籤。

    // 自己列出缺什麼，卻又宣稱資料充足 —— 這是最常見的自我矛盾。
    if (output.evidenceReview.missingForQuestion.length > 0 && output.dataSufficiency === 'sufficient') {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['dataSufficiency'],
        message:
          'evidenceReview.missingForQuestion 非空（自己列出了缺少的資料），dataSufficiency 就不可以是 sufficient，至少是 partial。',
      });
    }

    // 說資料不足，卻說不出缺什麼，等於沒有真的判斷過。
    if (output.dataSufficiency === 'insufficient' && output.evidenceReview.missingForQuestion.length === 0) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['evidenceReview', 'missingForQuestion'],
        message:
          'dataSufficiency 為 insufficient 時，evidenceReview.missingForQuestion 必須列出缺少哪些資料。',
      });
    }

    // 原本這裡有一條「availableMetrics 為空卻寫出結論 → 擋掉」。
    //
    // 那條規則的目的是抓「模型說自己沒看到任何指標，卻還是寫了結論」這種自我矛盾。
    // 但 `availableMetrics` 現在是**程式**從 `context.evidence` 盤點出來的，
    // 模型碰不到，所以它不可能在這件事上自我矛盾 —— 這條檢查已經沒有對象。
    //
    // 而它原本要保護的性質仍然成立，只是換了地方把關：
    // 「沒有任何可引用的資料就不該呼叫模型」由 `shouldReportInsufficientData()` 負責，
    // 「結論必須有引用」由上面的 hasAnyCitation 檢查負責。
    //
    // 留著反而有害：模型的原始回應裡 availableMetrics 一定是空的（它不輸出那個欄位），
    // 於是每一個有結論的正常回應都會被誤判成違規。

    // 用了網路資料，就不可能是 sufficient。
    //
    // 理由：如果資料管線的 evidence 已經足夠回答問題，就不需要上網。反過來說，
    // 一旦引用了網路來源，代表管線資料有缺口 —— 那個缺口必須被標示出來，
    // 不可以因為「上網補到了」就宣稱資料充足。這條規則讓網路搜尋不會變成
    // 掩蓋資料缺口的手段。
    if (output.webReferences.length > 0 && output.dataSufficiency === 'sufficient') {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['dataSufficiency'],
        message:
          '引用了網路來源（webReferences 非空）就不可以是 sufficient：需要上網補充代表資料管線有缺口，那個缺口必須誠實標示。',
      });
    }

    // 用了網路資料卻沒在 limitations 說明，使用者會以為那些內容跟官方統計同等可信。
    if (
      output.webReferences.length > 0 &&
      !output.limitations.some((note) => note.includes('網路'))
    ) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['limitations'],
        message:
          '引用了網路來源時，limitations 必須有一條說明「部分內容來自網路搜尋，非資料管線的官方統計」。',
      });
    }
  });
export type StructuredOutput = z.infer<typeof StructuredOutputSchema>;

/**
 * 檢查 webReferences 是否只引用了真的存在的 findingId。
 * 跟 `findUnknownEvidenceIds` 同理：schema 看不到當次 context，只能在 handler 驗。
 * 網路來源尤其重要 —— 模型很容易「記得」一個看起來合理但這次沒給它的網址。
 */
export function findUnknownFindingIds(
  output: StructuredOutput,
  knownFindingIds: readonly string[],
): string[] {
  const known = new Set(knownFindingIds);
  return [...new Set(output.webReferences.map((reference) => reference.findingId))].filter(
    (findingId) => !known.has(findingId),
  );
}

/**
 * 檢查 basis 是否只引用了真的存在的 evidenceId。
 *
 * 這條規則沒辦法寫進 `StructuredOutputSchema`，因為 schema 看不到當次的 context。
 * 但這是「不可捏造」最容易被違反的地方——模型很容易把 evidenceId 拼錯或自己組一個
 * 看起來合理的 ID——所以一定要有一層獨立檢查。
 */
export function findUnknownEvidenceIds(
  output: StructuredOutput,
  knownEvidenceIds: readonly string[],
): string[] {
  const known = new Set(knownEvidenceIds);
  return [...new Set(output.basis.map((citation) => citation.evidenceId))].filter(
    (evidenceId) => !known.has(evidenceId),
  );
}
