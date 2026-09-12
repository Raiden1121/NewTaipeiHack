import { create } from "zustand";
import { persist } from "zustand/middleware";

export type FontSize = "sm" | "md" | "lg";
export type ColorTheme =
  | "blue"
  | "indigo"
  | "teal"
  | "amber"
  | "rose"
  | "slate";
export type DarkModePreference = "light" | "dark" | "system";
export type Density = "comfortable" | "compact";

interface SettingsValues {
  fontSize: FontSize;
  colorTheme: ColorTheme;
  darkMode: DarkModePreference;
  density: Density;
  highContrast: boolean;
  reduceMotion: boolean;
}

interface SettingsState extends SettingsValues {
  setFontSize: (fontSize: FontSize) => void;
  setColorTheme: (colorTheme: ColorTheme) => void;
  setDarkMode: (darkMode: DarkModePreference) => void;
  setDensity: (density: Density) => void;
  setHighContrast: (highContrast: boolean) => void;
  setReduceMotion: (reduceMotion: boolean) => void;
  resetToDefaults: () => void;
}

export const DEFAULT_SETTINGS: SettingsValues = {
  fontSize: "md",
  colorTheme: "blue",
  darkMode: "system",
  density: "comfortable",
  highContrast: false,
  reduceMotion: false,
};

export const useSettingsStore = create<SettingsState>()(
  persist(
    (set) => ({
      ...DEFAULT_SETTINGS,
      setFontSize: (fontSize) => set({ fontSize }),
      setColorTheme: (colorTheme) => set({ colorTheme }),
      setDarkMode: (darkMode) => set({ darkMode }),
      setDensity: (density) => set({ density }),
      setHighContrast: (highContrast) => set({ highContrast }),
      setReduceMotion: (reduceMotion) => set({ reduceMotion }),
      resetToDefaults: () => set(DEFAULT_SETTINGS),
    }),
    { name: "newtaipei-youth-settings" },
  ),
);
