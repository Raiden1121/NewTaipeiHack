// 機會指數 choropleth 著色。顏色於執行期依「資料數值」與「使用者選擇的主色調」
// 兩者計算後寫入 SVG 內聯 style，為 CLAUDE.md 允許之硬寫色碼例外（唯一用途：地圖填色）。
import type { ColorTheme } from "@/stores/useSettingsStore";

// 每個主色調各一組 3 階漸層（淺→深），供三種 choropleth 共用。
// indigo/teal/amber/rose 四組錨定在設定頁色票的實際品牌色（紫色/綠/橘色/粉紅），
// 淺色階由該品牌色往白色線性內插 lightness 算出，深色階即品牌色本身。
const THEME_PALETTES: Record<ColorTheme, [string, string, string]> = {
  blue: ["#e3edf7", "#7fb0dd", "#0a5aa8"],
  indigo: ["#ede0f5", "#b479d6", "#722F99"],
  teal: ["#e6edef", "#9fb9c2", "#5c8391"],
  amber: ["#ffe8d6", "#ffc598", "#FFA259"],
  rose: ["#fbdada", "#f9c3c3", "#F7ADAD"],
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

// 每個主色調各一組 5 階漸層（淺→深），供青年參政地圖固定門檻著色專用。
const PARTICIPATION_PALETTES: Record<
  ColorTheme,
  [string, string, string, string, string]
> = {
  blue: ["#e3edf7", "#b1cfea", "#7fb0dd", "#4585c3", "#0a5aa8"],
  indigo: ["#ede0f5", "#d1ace6", "#b479d6", "#9745c6", "#722F99"],
  teal: ["#e6edef", "#c3d3d9", "#9fb9c2", "#7b9fac", "#5c8391"],
  amber: ["#ffe8d6", "#ffd7b7", "#ffc598", "#ffb478", "#FFA259"],
  rose: ["#fbdada", "#facfcf", "#f9c3c3", "#f8b8b8", "#F7ADAD"],
  slate: ["#e6eaef", "#bfc8d3", "#98a6b6", "#6e7e91", "#43566b"],
};

// 青年參政地圖固定五階門檻（每十萬青年候選人參選率）。真實資料絕大多數行政區落在
// 個位數～20 之間、最高約 60 出頭（烏來、瑞芳等偏鄉因青年人口基數小而參選率偏高），
// 分布與 0–100 常見指數級距差異極大，故此圖不用 computeTercileThresholds() 動態算，
// 改為固定門檻——如未來真實資料分布明顯位移，需回來手動調整這組數字。
const PARTICIPATION_THRESHOLDS = [3, 8, 15, 30] as const;

export function participationFillColor(
  value: number | null | undefined,
  colorTheme: ColorTheme,
): string {
  const palette = PARTICIPATION_PALETTES[colorTheme];
  if (value === null || value === undefined) return palette[0];
  if (value >= PARTICIPATION_THRESHOLDS[3]) return palette[4];
  if (value >= PARTICIPATION_THRESHOLDS[2]) return palette[3];
  if (value >= PARTICIPATION_THRESHOLDS[1]) return palette[2];
  if (value >= PARTICIPATION_THRESHOLDS[0]) return palette[1];
  return palette[0];
}

export const SELECTED_DISTRICT_FILL = "#ffad5a";
