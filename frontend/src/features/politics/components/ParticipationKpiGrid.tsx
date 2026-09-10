import { useMemo } from "react";
import { motion } from "motion/react";
import {
  ArrowLeftRight,
  Building2,
  Gauge,
  Layers,
  TrendingDown,
  UserPlus,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { useDistrictSummary } from "@/features/home/hooks/useDistrictSummary";
import { useSelectedDistrict } from "@/stores/useSelectedDistrict";
import { Card, CardContent } from "@/components/ui/card";
import { buildParticipationMetrics } from "../placeholderMetrics";
import { cn } from "@/lib/utils";

const ICONS: Record<string, LucideIcon> = {
  "candidate-density": UserPlus,
  "youth-borough-chief": Building2,
  "lean-ratio": ArrowLeftRight,
  yrr: Gauge,
  "elected-gap": TrendingDown,
  "generation-gap": Layers,
};

export default function ParticipationKpiGrid() {
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
  const metrics = useMemo(
    () => buildParticipationMetrics(seedKey),
    [seedKey],
  );

  return (
    <div className="flex flex-col gap-3">
      <p className="text-xs font-semibold text-accent-slate">
        目前檢視範圍：
        <span className="font-bold text-slate-700">{scopeLabel}</span>
        {selectedDistrict ? "（點選地圖或右側排名切換）" : "（點選地圖選擇行政區）"}
      </p>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {metrics.map((metric, index) => {
          const Icon = ICONS[metric.id] ?? Gauge;
          const isNegativeValue = metric.negative && metric.value < 0;
          return (
            <motion.div
              key={metric.id}
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: index * 0.05, duration: 0.3 }}
            >
              <Card className="h-full">
                <CardContent className="flex items-start justify-between gap-3 p-5">
                  <div>
                    <p className="text-sm font-semibold text-slate-600">
                      {metric.label}
                    </p>
                    <p
                      className={cn(
                        "mt-1 text-3xl font-bold",
                        isNegativeValue ? "text-risk-high" : "text-slate-900",
                      )}
                    >
                      {metric.format(metric.value)}
                    </p>
                    <p className="mt-1 text-xs text-slate-400">
                      {metric.caption}
                    </p>
                  </div>
                  <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
                    <Icon className="h-4 w-4" aria-hidden="true" />
                  </span>
                </CardContent>
              </Card>
            </motion.div>
          );
        })}
      </div>
      <p className="text-[11px] text-slate-400">
        六大參政指標為依行政區產生的佔位資料，待 Backend API 提供整理後結果。
      </p>
    </div>
  );
}
