import { useLocation } from "react-router-dom";
import { useSettingsStore, type ColorTheme } from "@/stores/useSettingsStore";

// 各頁面的預設主色調。使用者尚未在設定頁手動選色（useCustomColor === false）
// 時採用，讓不同板塊有各自識別色；一旦手動選色，全站改採單一 colorTheme，
// 直到「重置為預設值」才會跳回這裡。務必與 index.html 內防閃爍腳本中的
// 同一份對照表保持一致。
export const PAGE_DEFAULT_COLOR_THEME: Record<string, ColorTheme> = {
  "/": "teal", // 主頁 → 綠
  "/employment": "blue", // 青年就業 → 藍
  "/politics": "amber", // 青年參政 → 橘色
  "/fertility": "rose", // 青年生育 → 粉紅
  "/policy-support": "teal", // 施政協助 → 綠
};

export function useEffectiveColorTheme(): ColorTheme {
  const { pathname } = useLocation();
  const colorTheme = useSettingsStore((state) => state.colorTheme);
  const useCustomColor = useSettingsStore((state) => state.useCustomColor);
  return useCustomColor ? colorTheme : (PAGE_DEFAULT_COLOR_THEME[pathname] ?? "blue");
}
