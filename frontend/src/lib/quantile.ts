function quantile(sortedValues: number[], q: number): number {
  if (sortedValues.length === 0) return 0;
  if (sortedValues.length === 1) return sortedValues[0];
  const pos = (sortedValues.length - 1) * q;
  const base = Math.floor(pos);
  const rest = pos - base;
  const next = sortedValues[base + 1];
  return next !== undefined
    ? sortedValues[base] + rest * (next - sortedValues[base])
    : sortedValues[base];
}

/**
 * 依實際資料動態算三等分（33rd / 67th 百分位）門檻，取代寫死門檻。
 * 用於 choropleth 三階漸層著色：避免真實值域與寫死門檻不符，導致地圖幾乎全白。
 * 見 api_contract.md §10 已知問題 #2。
 */
export function computeTercileThresholds(values: number[]): [number, number] {
  const sorted = [...values].filter((v) => Number.isFinite(v)).sort((a, b) => a - b);
  if (sorted.length === 0) return [0, 0];
  return [quantile(sorted, 1 / 3), quantile(sorted, 2 / 3)];
}
