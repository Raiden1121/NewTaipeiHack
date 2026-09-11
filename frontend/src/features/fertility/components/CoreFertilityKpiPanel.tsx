import { useMemo } from "react";
import { motion } from "motion/react";
import { Baby, CalendarClock, HeartPulse, Home, Users } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { useDistrictSummary } from "@/features/home/hooks/useDistrictSummary";
import { useSelectedDistrict } from "@/stores/useSelectedDistrict";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { buildFertilityMetrics } from "../placeholderMetrics";
import { cn } from "@/lib/utils";

const ICONS: Record<string, LucideIcon> = {
  "total-births": Baby,
  "avg-fertility-rate": HeartPulse,
  "youth-population-share": Users,
  "childcare-coverage": Home,
};

export default function CoreFertilityKpiPanel() {
  const { data: districts = [] } = useDistrictSummary();
  const selectedDistrictId = useSelectedDistrict(
    (state) => state.selectedDistrictId,
  );

  const selectedDistrict = useMemo(
    () => districts.find((district) => district.id === selectedDistrictId) ?? null,
    [districts, selectedDistrictId],
  );

  const seedKey = selectedDistrict ? selectedDistrict.id : "city-wide";
  const scopeLabel = selectedDistrict ? selectedDistrict.name : "全市";
  const metrics = useMemo(() => buildFertilityMetrics(seedKey), [seedKey]);

  // 全市平均基準值，用於各指標卡右側「較全市平均」框框；固定 seed，不隨選取變動。
  const cityMetrics = useMemo(() => buildFertilityMetrics("city-wide"), []);
  const cityValueById = useMemo(
    () => new Map(cityMetrics.map((metric) => [metric.id, metric.value])),
    [cityMetrics],
  );

  return (
    <Card className="flex h-full flex-col">
      <CardHeader>
        <p className="text-xs font-bold uppercase tracking-[0.16em] text-accent-slate">
          Core Metrics
        </p>
        <div className="flex items-start justify-between gap-2">
          <CardTitle className="text-lg font-bold text-slate-900">
            核心生育指標
          </CardTitle>
          <span className="inline-flex shrink-0 items-center gap-1 rounded-full bg-primary/10 px-2 py-0.5 text-[11px] font-semibold text-primary">
            <CalendarClock className="h-3 w-3" aria-hidden="true" />
            與去年相比
          </span>
        </div>
        <p className="text-xs font-semibold text-accent-slate">
          目前檢視範圍：
          <span className="font-bold text-slate-700">{scopeLabel}</span>
          {selectedDistrict ? "（點選地圖切換）" : "（點選地圖選擇行政區）"}
        </p>
      </CardHeader>
      <CardContent className="flex flex-1 flex-col gap-2.5">
        {metrics.map((metric, index) => {
          const Icon = ICONS[metric.id] ?? Baby;
          const hasDelta = metric.deltaPct !== undefined;
          const isPositiveDelta = (metric.deltaPct ?? 0) >= 0;

          // 較全市平均：僅在選取特定行政區時計算，檢視「全市」本身時無比較對象。
          const cityValue = cityValueById.get(metric.id);
          const avgDiffPct =
            selectedDistrict && cityValue
              ? Math.round(((metric.value - cityValue) / cityValue) * 1000) / 10
              : null;

          return (
            <motion.div
              key={metric.id}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: index * 0.04, duration: 0.28 }}
              className="flex flex-1 items-center gap-3 rounded-xl border border-slate-200 bg-slate-50 px-4 py-3"
            >
              <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
                <Icon className="h-4 w-4" aria-hidden="true" />
              </span>
              <div className="min-w-0 flex-1">
                <p className="text-xs font-semibold text-slate-600">
                  {metric.label}
                </p>
                <p className="mt-1 flex items-baseline gap-1.5">
                  <span className="text-2xl font-bold text-slate-900">
                    {metric.format(metric.value)}
                  </span>
                  {hasDelta ? (
                    <span
                      className={cn(
                        "text-xs font-bold",
                        isPositiveDelta ? "text-risk-low" : "text-risk-high",
                      )}
                    >
                      {isPositiveDelta ? "+" : ""}
                      {metric.deltaPct}%
                    </span>
                  ) : null}
                </p>
                <p className="mt-1 text-[11px] text-slate-400">
                  {metric.caption}
                </p>
              </div>
              <span
                className={cn(
                  "flex w-14 shrink-0 flex-col items-center justify-center rounded-md border px-1.5 py-1 text-center leading-tight",
                  avgDiffPct === null
                    ? "border-slate-200 bg-slate-100 text-slate-400"
                    : avgDiffPct > 0
                      ? "border-risk-high/30 bg-risk-high/10 text-risk-high"
                      : avgDiffPct < 0
                        ? "border-risk-low/30 bg-risk-low/10 text-risk-low"
                        : "border-slate-200 bg-slate-100 text-slate-400",
                )}
              >
                <span className="text-[9px] font-semibold uppercase tracking-wide opacity-70">
                  較平均
                </span>
                <span className="text-xs font-bold">
                  {avgDiffPct === null
                    ? "－"
                    : `${avgDiffPct > 0 ? "+" : ""}${avgDiffPct}%`}
                </span>
              </span>
            </motion.div>
          );
        })}
        <p className="pt-1 text-[11px] text-slate-400">
          四項生育指標為依行政區產生的佔位資料。行內百分比為與去年同期相比，右側框框為與全市平均值相比（紅色代表較高、綠色代表較低），待
          Backend API 提供整理後結果。
        </p>
      </CardContent>
    </Card>
  );
}
