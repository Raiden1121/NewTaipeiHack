import { DISCLAIMER_KEYWORD } from './structuredOutput.js';

/**
 * 給 Bedrock Structured Outputs 用的 JSON Schema（六塊輸出）。
 *
 * 為什麼是手寫、不是從 zod 自動產生：
 * Bedrock 的 structured outputs 只吃 JSON Schema Draft 2020-12 的**子集**，
 * 而我們的 zod schema 用了好幾個不在子集裡的東西。踩到不支援的功能不是靜默忽略，
 * 是直接回 400（見 Bedrock 使用手冊 Structured outputs 的 Request workflow）。
 *
 * 明確不支援、所以這裡刻意不出現的：
 * - `minLength` / `maxLength`（字串長度）→ 所以 `.min(1)` 不能翻成 minLength
 * - `minimum` / `maximum` / `multipleOf`（數值範圍）
 * - `additionalProperties` 設成 false 以外的值
 * - 遞迴 schema、外部 `$ref`
 * - 陣列 `minItems` 只允許 0 和 1（`basis` 的 minItems: 1 剛好在允許範圍內）
 *
 * 所以驗證是**兩道關卡**，各有分工：
 * 1. Bedrock structured outputs 保證「形狀對」（欄位齊全、型別正確、沒有多餘欄位）
 * 2. `StructuredOutputSchema.parse()` 保證「語意對」（disclaimer 含固定字樣、
 *    basis 至少一筆、字串非空）
 *
 * 少了第 2 道，模型可以回一個形狀完全合法但 disclaimer 是空字串的東西。
 */
export const STRUCTURED_OUTPUT_JSON_SCHEMA = {
  type: 'object',
  properties: {
    // ⚠️ evidenceReview 必須排在第一個。JSON 是依欄位順序生成的，所以把「盤點」
    // 放在所有結論之前，模型才會真的先盤點再下結論，而不是先寫結論再回頭湊 basis。
    // 調整這裡的欄位順序等於改變模型的思考順序。
    // ⚠️ 這裡刻意**只有** missingForQuestion 一個欄位。
    //
    // `availableMetrics` / `youthSpecificMetrics` / `contextOnlyMetrics` 由程式從
    // `context.evidence` 盤點（見 `handlers/evidenceInventory.ts`），不叫模型寫。
    // 實測模型花了整體輸出的 35% 在重打那三份清單，而內容沒有任何判斷成分。
    //
    // 因為 `additionalProperties: false`，這裡沒列出來的欄位模型**不能**輸出，
    // 所以這個 schema 同時是「不要寫那三個」的強制手段，不只是省略。
    evidenceReview: {
      type: 'object',
      description:
        '第 1 步：盤點這次拿到的 evidence。這一步只做描述不做判斷，且必須在寫任何結論之前完成。' +
        '指標清單由系統自動盤點，你只需要判斷「還缺什麼」。',
      properties: {
        missingForQuestion: {
          type: 'array',
          description:
            '要回答眼前這個問題還缺哪些資料。非空時 dataSufficiency 就不可以是 sufficient。沒有缺就填空陣列。',
          items: { type: 'string' },
        },
      },
      required: ['missingForQuestion'],
      additionalProperties: false,
    },
    dataSufficiency: {
      type: 'string',
      enum: ['sufficient', 'partial', 'insufficient'],
      description:
        '第 2 步：依規則判斷充足度，不要憑感覺。' +
        'insufficient=evidence 完全無法回答被問的問題，此時四塊結論必須全部留空、只寫 limitations；' +
        'partial=部分面向缺漏，只要 missingForQuestion 非空就至少是 partial；' +
        'sufficient=問題涵蓋的每個面向都有對應 evidence 且沒有需保留的解讀限制（最少見，判定前請再確認一次）。',
    },
    issues: {
      type: 'array',
      description: '問題辨識：從 evidence 看得出來的問題。沒有發現問題時回空陣列。',
      items: { type: 'string' },
    },
    strengths: {
      type: 'array',
      description: '發展優勢：從 evidence 看得出來的相對優勢。沒有時回空陣列。',
      items: { type: 'string' },
    },
    resourceGaps: {
      type: 'array',
      description: '資源缺口：青年需求與資源供給之間的落差。沒有時回空陣列。',
      items: { type: 'string' },
    },
    policyDirections: {
      type: 'array',
      description: '政策方向：可考慮的方向。沒有時回空陣列。',
      items: { type: 'string' },
    },
    // 刻意不設 minItems：資料不足（dataSufficiency=insufficient）時 basis 允許為空。
    // 「有結論就要有依據」這條條件式規則沒辦法用 Bedrock 支援的 JSON Schema 子集表達
    // （if/then/else 不支援），所以交給 StructuredOutputSchema 的 superRefine 把關。
    basis: {
      type: 'array',
      description:
        '判斷依據：資料管線 evidence 的引用。只能引用 context 裡真的存在的 evidenceId。' +
        '只要有任何結論，basis 或 webReferences 至少要有一筆。' +
        '若本次完全沒有 evidence（只有網路搜尋結果），basis 就填空陣列，' +
        '不要把 findingId 塞進來。',
      items: {
        type: 'object',
        properties: {
          evidenceId: {
            type: 'string',
            description: '必須是這次 context 裡真的存在的 evidenceId，不可發明',
          },
          note: {
            anyOf: [{ type: 'string' }, { type: 'null' }],
            description: '這筆 evidence 如何支持前面的判斷；沒有補充說明時用 null',
          },
        },
        required: ['evidenceId', 'note'],
        additionalProperties: false,
      },
    },
    webReferences: {
      type: 'array',
      description:
        '網路來源引用。只能引用 context 的「網路搜尋結果」區塊裡真的存在的 findingId；' +
        '沒有使用網路資料時填空陣列。網路內容不可當作權威統計數字，' +
        'note 要寫成「根據網路資料…」的語氣。',
      items: {
        type: 'object',
        properties: {
          findingId: {
            type: 'string',
            description: '必須是 context 的網路搜尋結果裡真的存在的 findingId，不可發明',
          },
          note: {
            anyOf: [{ type: 'string' }, { type: 'null' }],
            description: '這筆網路資料補充了什麼',
          },
        },
        required: ['findingId', 'note'],
        additionalProperties: false,
      },
    },
    limitations: {
      type: 'array',
      description:
        '資料限制：**只寫 context 的「已知的資料限制」沒有提到的新限制。**' +
        '已知限制由系統自動附加到最終輸出，不要抄寫進來（抄寫會浪費大量輸出、拖慢回應）。' +
        '若使用了網路資料，必須有一條說明「部分內容來自網路搜尋，非資料管線的官方統計」。' +
        '若本次完全沒有資料管線的 evidence（basis 為空、只有網路來源），' +
        '必須有一條明確說明「本次沒有資料管線的官方統計，以下內容僅來自網路搜尋」。' +
        '沒有任何限制時仍要回空陣列。',
      items: { type: 'string' },
    },
    disclaimer: {
      type: 'string',
      description: `免責聲明，必須包含「${DISCLAIMER_KEYWORD}」字樣`,
    },
  },
  required: [
    'evidenceReview',
    'dataSufficiency',
    'issues',
    'strengths',
    'resourceGaps',
    'policyDirections',
    'basis',
    'webReferences',
    'limitations',
    'disclaimer',
  ],
  additionalProperties: false,
} as const;

export const STRUCTURED_OUTPUT_SCHEMA_NAME = 'youth_policy_structured_output';
export const STRUCTURED_OUTPUT_SCHEMA_DESCRIPTION =
  '新北青年 Dashboard 的六塊分析輸出：問題辨識、發展優勢、資源缺口、政策方向、判斷依據、資料限制。';

/** Bedrock 的 `outputConfig.textFormat.structure.jsonSchema.schema` 要求是 JSON **字串**，不是物件。 */
export function structuredOutputSchemaJson(): string {
  return JSON.stringify(STRUCTURED_OUTPUT_JSON_SCHEMA);
}

/**
 * AI Data Q&A 專用的 JSON Schema。
 *
 * 跟六塊的差別只有兩件事：多一個 `answer`，以及四塊分析的說明改成
 * 「只有政策類問題才填」。
 *
 * ## 為什麼四塊仍然留在 `required` 裡
 *
 * 直覺上「選填」應該是把它們從 `required` 拿掉。但 Bedrock structured outputs
 * 對 schema 子集的限制很嚴（踩到不支援的寫法是直接回 400，不是靜默忽略），
 * 而「部分屬性不在 required」在各家 strict 模式的支援度不一致 ——
 * 拿 demo 前一天去試這件事風險太高。
 *
 * 所以改成：**欄位保留、由 description 指示模型在非政策類問題時填空陣列**。
 * 代價只有 `"issues":[],"strengths":[],"resourceGaps":[],"policyDirections":[],`
 * 這四個空陣列的 token（約 30 個），實質效果跟選填一樣，
 * 而且完全不動 Bedrock 的相容性。
 *
 * 順序仍然有意義：`evidenceReview` → `dataSufficiency` → `answer` → `basis` →
 * 四塊 → `limitations`。先盤點、再判斷充足度、才回答，最後補依據與限制。
 */
export const QA_OUTPUT_JSON_SCHEMA = {
  type: 'object',
  properties: {
    evidenceReview: STRUCTURED_OUTPUT_JSON_SCHEMA.properties.evidenceReview,
    dataSufficiency: {
      ...STRUCTURED_OUTPUT_JSON_SCHEMA.properties.dataSufficiency,
      description:
        '第 2 步：依規則判斷充足度，不要憑感覺。' +
        'insufficient=evidence 完全無法回答被問的問題，此時 answer 要直接說明無法回答、四塊留空；' +
        'partial=部分面向缺漏，只要 missingForQuestion 非空就至少是 partial；' +
        'sufficient=問題涵蓋的每個面向都有對應 evidence 且沒有需保留的解讀限制。',
    },
    answer: {
      type: 'string',
      description:
        '第 3 步：**直接回答使用者的問題。這是聊天框會顯示的內容。**' +
        '被問到具體數值時，第一句就要給出那個數值與單位，不要先講背景或分析。' +
        '**使用者的問題內含事實斷言時（例如「排第六高」），先用 evidence 查證；' +
        '斷言錯誤就在第一句溫和更正，再往下解釋。**' +
        '問「為什麼」時的結構：先確認或更正數字 → 同一份資料裡哪些指標方向一致 → ' +
        '網路資料補的背景（寫成「根據網路資料…（未經驗證）」）→ 這個解釋的不確定性。' +
        '**只能說「可能與…有關」「方向一致」，不可以寫成因果（「因為 A 所以 B」）。**' +
        '用完整的句子寫成可以直接讀給人聽的一段話（可以多句），不要用條列。' +
        '數字一律照抄 evidence，並在需要時註明它是 context_only / proxy_only。' +
        '如果資料不足以回答，就直接說明無法回答以及缺什麼，不要用相近但不同的指標硬答。',
    },
    basis: STRUCTURED_OUTPUT_JSON_SCHEMA.properties.basis,
    issues: {
      type: 'array',
      description:
        '問題辨識。**只有在使用者問的是政策類問題（例如「該怎麼改善」「有什麼建議」）時才填。**' +
        '單純查詢數值的問題請填空陣列 —— 不要為了填滿欄位而把 answer 的內容換句話再講一次。',
      items: { type: 'string' },
    },
    strengths: {
      type: 'array',
      description:
        '發展優勢。同上，只有政策類問題才填，否則空陣列。' +
        '**不要寫「資料管線已提供某些指標」這種關於資料本身的敘述** —— 那不是發展優勢。',
      items: { type: 'string' },
    },
    resourceGaps: {
      type: 'array',
      description: '資源缺口。同上，只有政策類問題才填，否則空陣列。',
      items: { type: 'string' },
    },
    policyDirections: {
      type: 'array',
      description: '政策方向。同上，只有政策類問題才填，否則空陣列。',
      items: { type: 'string' },
    },
    webReferences: STRUCTURED_OUTPUT_JSON_SCHEMA.properties.webReferences,
    limitations: STRUCTURED_OUTPUT_JSON_SCHEMA.properties.limitations,
    disclaimer: STRUCTURED_OUTPUT_JSON_SCHEMA.properties.disclaimer,
  },
  required: [
    'evidenceReview',
    'dataSufficiency',
    'answer',
    'basis',
    'issues',
    'strengths',
    'resourceGaps',
    'policyDirections',
    'webReferences',
    'limitations',
    'disclaimer',
  ],
  additionalProperties: false,
} as const;

export const QA_OUTPUT_SCHEMA_NAME = 'youth_policy_qa_answer';
export const QA_OUTPUT_SCHEMA_DESCRIPTION =
  '新北青年 Dashboard 的資料問答輸出：直接回答使用者的問題，附上可追溯的判斷依據與資料限制；' +
  '四塊政策分析只在使用者問政策類問題時才填。';

export function qaOutputSchemaJson(): string {
  return JSON.stringify(QA_OUTPUT_JSON_SCHEMA);
}

/**
 * Bedrock structured outputs 不支援的 JSON Schema 關鍵字。
 * 匯出給測試用：schema 一旦不小心長出這些關鍵字，就會在 CI 被擋下來，
 * 而不是等到 demo 現場才吃 400。
 */
export const UNSUPPORTED_JSON_SCHEMA_KEYWORDS: readonly string[] = [
  'minLength',
  'maxLength',
  'minimum',
  'maximum',
  'exclusiveMinimum',
  'exclusiveMaximum',
  'multipleOf',
  'maxItems',
  'uniqueItems',
  'patternProperties',
  'not',
  'if',
  'then',
  'else',
];
