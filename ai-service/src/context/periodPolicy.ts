/**
 * Resolve the period sent to repositories. Explicit request input wins; a
 * three-digit ROC year written in the user's question is the fallback.
 */
export function resolveQueryPeriod(
  period: string | null | undefined,
  question: string | null | undefined,
): string | undefined {
  const explicit = period?.trim();
  if (explicit !== undefined && explicit.length > 0) {
    return explicit;
  }

  if (typeof question !== 'string') {
    return undefined;
  }
  const match = question.match(/(?<!\d)(\d{3})\s*年(?:度)?/);
  return match?.[1];
}
