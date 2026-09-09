// 機會指數 choropleth 著色。顏色於執行期依資料計算後寫入 SVG 內聯 style，
// 為 CLAUDE.md 允許之硬寫色碼例外（唯一用途：地圖填色）。

export function opportunityFillColor(opportunityIndex: number | undefined): string {
  if (opportunityIndex === undefined) return "#d8e3ee";
  if (opportunityIndex >= 80) return "#0a5aa8";
  if (opportunityIndex >= 70) return "#3b82c8";
  if (opportunityIndex >= 60) return "#7fb0dd";
  if (opportunityIndex >= 50) return "#b9d4ec";
  return "#e3edf7";
}

// 青年參政指數 choropleth 著色。門檻比照 opportunityFillColor，
// 同屬地圖 choropleth 內聯色碼例外（唯一用途：地圖填色）。
export function participationFillColor(
  participationIndex: number | undefined,
): string {
  if (participationIndex === undefined) return "#d8e3ee";
  if (participationIndex >= 70) return "#0a5aa8";
  if (participationIndex >= 62) return "#3b82c8";
  if (participationIndex >= 54) return "#7fb0dd";
  if (participationIndex >= 46) return "#b9d4ec";
  return "#e3edf7";
}

export const SELECTED_DISTRICT_FILL = "#ffad5a";
