import { useEffect } from "react";
import { useSettingsStore } from "@/stores/useSettingsStore";
import { useEffectiveColorTheme } from "@/hooks/useEffectiveColorTheme";

const FONT_SIZE_PX: Record<string, string> = {
  sm: "14px",
  md: "16px",
  lg: "18px",
};

/** 無 UI 的旁路元件：把設定值反映到 <html> 的 class/data attribute。 */
export default function SettingsEffects() {
  const fontSize = useSettingsStore((state) => state.fontSize);
  const colorTheme = useEffectiveColorTheme();
  const darkMode = useSettingsStore((state) => state.darkMode);
  const density = useSettingsStore((state) => state.density);
  const highContrast = useSettingsStore((state) => state.highContrast);

  useEffect(() => {
    const root = document.documentElement;
    const media = window.matchMedia("(prefers-color-scheme: dark)");

    const applyDark = () => {
      const isDark = darkMode === "dark" || (darkMode === "system" && media.matches);
      root.classList.toggle("dark", isDark);
    };

    applyDark();

    if (darkMode === "system") {
      media.addEventListener("change", applyDark);
      return () => media.removeEventListener("change", applyDark);
    }
  }, [darkMode]);

  useEffect(() => {
    document.documentElement.dataset.themeColor = colorTheme;
  }, [colorTheme]);

  useEffect(() => {
    document.documentElement.dataset.density = density;
  }, [density]);

  useEffect(() => {
    document.documentElement.classList.toggle("high-contrast", highContrast);
  }, [highContrast]);

  useEffect(() => {
    document.documentElement.style.fontSize = FONT_SIZE_PX[fontSize] ?? FONT_SIZE_PX.md;
  }, [fontSize]);

  return null;
}
