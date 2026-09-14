import { DISCLAIMER_KEYWORD, QaOutputSchema, type StructuredOutput } from '../types/structuredOutput.js';

/** 純問候不需要統計證據；只有整句都是問候才走這條路。 */
export function isSimpleGreeting(question: string | null | undefined): boolean {
  return typeof question === 'string' && /^(?:你好|您好|嗨|哈囉|hi|hello)[\s!！。?？]*$/iu.test(question.trim());
}

export function buildGreetingOutput(): StructuredOutput {
  const reason = '尚未提出資料查詢問題。';
  return QaOutputSchema.parse({
    evidenceReview: { missingForQuestion: [reason] },
    dataSufficiency: 'insufficient',
    answer: '你好！我可以協助查詢新北市各區的青年人口、就業與居住資料。想先了解哪一區？',
    issues: [],
    strengths: [],
    resourceGaps: [],
    policyDirections: [],
    basis: [],
    webReferences: [],
    limitations: [reason],
    disclaimer: `AI 建議屬於政策輔助資訊，${DISCLAIMER_KEYWORD}。`,
  });
}
