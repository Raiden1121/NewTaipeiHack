import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { Settings, X, RotateCcw } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { cn } from "@/lib/utils";
import {
  useSettingsStore,
  type ColorTheme,
  type DarkModePreference,
  type Density,
  type FontSize,
} from "@/stores/useSettingsStore";

const FONT_SIZE_OPTIONS: { value: FontSize; label: string }[] = [
  { value: "sm", label: "小" },
  { value: "md", label: "中" },
  { value: "lg", label: "大" },
];

const DARK_MODE_OPTIONS: { value: DarkModePreference; label: string }[] = [
  { value: "light", label: "淺色" },
  { value: "dark", label: "深色" },
  { value: "system", label: "跟隨系統" },
];

const DENSITY_OPTIONS: { value: Density; label: string }[] = [
  { value: "comfortable", label: "舒適" },
  { value: "compact", label: "精簡" },
];

const COLOR_THEME_OPTIONS: {
  value: ColorTheme;
  label: string;
  swatchClassName: string;
}[] = [
  { value: "blue", label: "藍", swatchClassName: "bg-blue-700" },
  { value: "indigo", label: "靛紫", swatchClassName: "bg-indigo-600" },
  { value: "teal", label: "青綠", swatchClassName: "bg-teal-600" },
  { value: "amber", label: "暖橘", swatchClassName: "bg-amber-500" },
  { value: "rose", label: "玫瑰紅", swatchClassName: "bg-rose-600" },
  { value: "slate", label: "石板灰", swatchClassName: "bg-slate-600" },
];

interface SegmentedControlProps<T extends string> {
  value: T;
  options: { value: T; label: string }[];
  onChange: (value: T) => void;
  "aria-label": string;
}

function SegmentedControl<T extends string>({
  value,
  options,
  onChange,
  ...props
}: SegmentedControlProps<T>) {
  return (
    <div
      className="inline-flex rounded-lg border border-slate-200 bg-slate-50 p-1 dark:border-slate-700 dark:bg-slate-800"
      role="group"
      aria-label={props["aria-label"]}
    >
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          aria-pressed={value === option.value}
          onClick={() => onChange(option.value)}
          className={cn(
            "rounded-md px-3 py-1 text-xs font-semibold transition-colors",
            value === option.value
              ? "bg-primary text-primary-foreground shadow-sm"
              : "text-slate-600 hover:text-slate-900 dark:text-slate-300 dark:hover:text-white",
          )}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}

interface SettingRowProps {
  label: string;
  children: React.ReactNode;
}

function SettingRow({ label, children }: SettingRowProps) {
  return (
    <div className="flex items-center justify-between gap-3">
      <span className="text-sm font-medium text-slate-700 dark:text-slate-200">
        {label}
      </span>
      {children}
    </div>
  );
}

export default function SettingsPanel() {
  const [open, setOpen] = useState(false);
  const panelRef = useRef<HTMLDivElement>(null);

  const fontSize = useSettingsStore((state) => state.fontSize);
  const colorTheme = useSettingsStore((state) => state.colorTheme);
  const darkMode = useSettingsStore((state) => state.darkMode);
  const density = useSettingsStore((state) => state.density);
  const highContrast = useSettingsStore((state) => state.highContrast);
  const reduceMotion = useSettingsStore((state) => state.reduceMotion);
  const setFontSize = useSettingsStore((state) => state.setFontSize);
  const setColorTheme = useSettingsStore((state) => state.setColorTheme);
  const setDarkMode = useSettingsStore((state) => state.setDarkMode);
  const setDensity = useSettingsStore((state) => state.setDensity);
  const setHighContrast = useSettingsStore((state) => state.setHighContrast);
  const setReduceMotion = useSettingsStore((state) => state.setReduceMotion);
  const resetToDefaults = useSettingsStore((state) => state.resetToDefaults);

  useEffect(() => {
    if (!open) return;

    function handlePointerDown(event: MouseEvent) {
      if (!panelRef.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    }

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }

    document.addEventListener("mousedown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("mousedown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [open]);

  return (
    <div ref={panelRef} className="fixed bottom-4 left-4 z-50">
      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: 8 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 8 }}
            transition={{ duration: 0.15, ease: "easeOut" }}
            className="absolute bottom-14 left-0 w-80 origin-bottom-left"
          >
            <Card className="max-h-[70vh] overflow-y-auto dark:bg-surface">
              <div className="flex items-center justify-between border-b border-slate-200 p-4 pb-3 dark:border-slate-700">
                <h2 className="text-sm font-bold text-slate-900 dark:text-white">
                  顯示設定
                </h2>
                <button
                  type="button"
                  onClick={() => setOpen(false)}
                  aria-label="關閉設定面板"
                  className="rounded-md p-1 text-slate-500 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800"
                >
                  <X className="h-4 w-4" aria-hidden="true" />
                </button>
              </div>

              <div className="flex flex-col gap-4 p-4">
                <SettingRow label="字體大小">
                  <SegmentedControl
                    aria-label="字體大小"
                    value={fontSize}
                    options={FONT_SIZE_OPTIONS}
                    onChange={setFontSize}
                  />
                </SettingRow>

                <div className="flex flex-col gap-2">
                  <span className="text-sm font-medium text-slate-700 dark:text-slate-200">
                    主色調
                  </span>
                  <div className="flex flex-wrap gap-2">
                    {COLOR_THEME_OPTIONS.map((option) => (
                      <button
                        key={option.value}
                        type="button"
                        aria-label={option.label}
                        aria-pressed={colorTheme === option.value}
                        onClick={() => setColorTheme(option.value)}
                        className={cn(
                          "h-7 w-7 rounded-full ring-offset-2 transition dark:ring-offset-slate-900",
                          option.swatchClassName,
                          colorTheme === option.value &&
                            "ring-2 ring-slate-900 dark:ring-white",
                        )}
                      />
                    ))}
                  </div>
                </div>

                <SettingRow label="深色模式">
                  <SegmentedControl
                    aria-label="深色模式"
                    value={darkMode}
                    options={DARK_MODE_OPTIONS}
                    onChange={setDarkMode}
                  />
                </SettingRow>

                <SettingRow label="資料密度">
                  <SegmentedControl
                    aria-label="資料密度"
                    value={density}
                    options={DENSITY_OPTIONS}
                    onChange={setDensity}
                  />
                </SettingRow>

                <SettingRow label="高對比模式">
                  <Switch
                    checked={highContrast}
                    onCheckedChange={setHighContrast}
                    aria-label="高對比模式"
                  />
                </SettingRow>

                <SettingRow label="減少動態效果">
                  <Switch
                    checked={reduceMotion}
                    onCheckedChange={setReduceMotion}
                    aria-label="減少動態效果"
                  />
                </SettingRow>

                <Button
                  variant="outline"
                  size="sm"
                  onClick={resetToDefaults}
                  className="mt-1 self-start"
                >
                  <RotateCcw className="mr-2 h-3.5 w-3.5" aria-hidden="true" />
                  重置為預設值
                </Button>
              </div>
            </Card>
          </motion.div>
        )}
      </AnimatePresence>

      <button
        type="button"
        onClick={() => setOpen((prev) => !prev)}
        aria-label="開啟顯示設定"
        aria-expanded={open}
        className="flex h-11 w-11 items-center justify-center rounded-full bg-primary text-primary-foreground shadow-lg transition-transform hover:scale-105"
      >
        <Settings className="h-5 w-5" aria-hidden="true" />
      </button>
    </div>
  );
}
