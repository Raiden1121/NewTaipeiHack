import { describe, expect, it, beforeEach } from "vitest";
import { DEFAULT_SETTINGS, useSettingsStore } from "./useSettingsStore";

describe("useSettingsStore", () => {
  beforeEach(() => {
    useSettingsStore.setState(DEFAULT_SETTINGS);
  });

  it("starts with the default settings", () => {
    expect(useSettingsStore.getState()).toMatchObject(DEFAULT_SETTINGS);
  });

  it("setFontSize updates the font size", () => {
    useSettingsStore.getState().setFontSize("lg");
    expect(useSettingsStore.getState().fontSize).toBe("lg");
  });

  it("setColorTheme updates the color theme", () => {
    useSettingsStore.getState().setColorTheme("teal");
    expect(useSettingsStore.getState().colorTheme).toBe("teal");
  });

  it("setDarkMode updates the dark mode preference", () => {
    useSettingsStore.getState().setDarkMode("dark");
    expect(useSettingsStore.getState().darkMode).toBe("dark");
  });

  it("resetToDefaults restores every value after changes", () => {
    const state = useSettingsStore.getState();
    state.setFontSize("lg");
    state.setColorTheme("rose");
    state.setDarkMode("dark");
    state.setDensity("compact");
    state.setHighContrast(true);
    state.setReduceMotion(true);

    useSettingsStore.getState().resetToDefaults();

    expect(useSettingsStore.getState()).toMatchObject(DEFAULT_SETTINGS);
  });
});
