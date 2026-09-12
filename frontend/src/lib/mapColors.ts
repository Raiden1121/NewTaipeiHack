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

// 三階門檻寫死值曾與真實值域完全不符（見 api_contract.md §10 #2），已改由呼叫端
// 用 computeTercileThresholds() 依當下資料動態算好再傳入。
export function tieredFillColor(
  value: number | null | undefined,
  thresholds: [number, number],
  colorTheme: ColorTheme,
): string {
  const palette = THEME_PALETTES[colorTheme];
  if (value === null || value === undefined) return palette[0];
  if (value >= thresholds[1]) return palette[2];
  if (value >= thresholds[0]) return palette[1];
  return palette[0];
}

export const SELECTED_DISTRICT_FILL = "#ffad5a";
