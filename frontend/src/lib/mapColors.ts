// 機會指數 choropleth 著色。顏色於執行期依「資料數值」與「使用者選擇的主色調」
// 兩者計算後寫入 SVG 內聯 style，為 CLAUDE.md 允許之硬寫色碼例外（唯一用途：地圖填色）。
import type { ColorTheme } from "@/stores/useSettingsStore";

// 每個主色調各一組 3 階漸層（淺→深），供三種 choropleth 共用。
const THEME_PALETTES: Record<ColorTheme, [string, string, string]> = {
  blue: ["#e3edf7", "#7fb0dd", "#0a5aa8"],
  indigo: ["#e6e4f7", "#9d94e0", "#4a3aab"],
  teal: ["#dcf3ef", "#6ec6b3", "#0f7d69"],
  amber: ["#fbeedd", "#edb46e", "#b56a1a"],
  rose: ["#fbe4ea", "#e888a8", "#a52457"],
  slate: ["#e6eaef", "#98a6b6", "#43566b"],
};

function tieredFillColor(
  value: number | undefined,
  thresholds: [number, number],
  colorTheme: ColorTheme,
): string {
  const palette = THEME_PALETTES[colorTheme];
  if (value === undefined) return palette[0];
  if (value >= thresholds[1]) return palette[2];
  if (value >= thresholds[0]) return palette[1];
  return palette[0];
}

export function opportunityFillColor(
  opportunityIndex: number | undefined,
  colorTheme: ColorTheme = "blue",
): string {
  return tieredFillColor(opportunityIndex, [60, 75], colorTheme);
}

// 青年參政指數 choropleth 著色。門檻比照 opportunityFillColor。
export function participationFillColor(
  participationIndex: number | undefined,
  colorTheme: ColorTheme = "blue",
): string {
  return tieredFillColor(participationIndex, [52, 62], colorTheme);
}

// 青年生育率 choropleth 著色。CSV fertilityRate 約落在 35–54 區間。
export function fertilityFillColor(
  fertilityRate: number | undefined,
  colorTheme: ColorTheme = "blue",
): string {
  return tieredFillColor(fertilityRate, [41, 46], colorTheme);
}

export const SELECTED_DISTRICT_FILL = "#ffad5a";
