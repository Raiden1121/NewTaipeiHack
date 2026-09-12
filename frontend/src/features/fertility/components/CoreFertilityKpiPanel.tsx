import { Baby, CalendarClock, HeartPulse, Users } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { useDistrictSummary } from "@/features/home/hooks/useDistrictSummary";
import { useDashboardOverview } from "@/lib/api/queries";
import { useSelectedDistrict } from "@/stores/useSelectedDistrict";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { formatInt, formatSignedPercent } from "@/lib/format";
import { cn } from "@/lib/utils";
import MetricInfoTooltip from "@/components/shared/MetricInfoTooltip";
import { FERTILITY_RATE_FORMULA } from "@/lib/metricFormulas";

interface Metric {
  id: string;
  icon: LucideIcon;
  label: string;
  caption: string;
  value: string;
  deltaPct: number | null;
  avgDiffPct: number | null;
  formula?: string;
}

export default function CoreFertilityKpiPanel() {
  const { data: districts = [] } = useDistrictSummary();
  const { data: overview, isLoading } = useDashboardOverview();
  const selectedDistrictId = useSelectedDistrict(
    (state) => state.selectedDistrictId,
  );

  const selectedDistrict = districts.find(
    (district) => district.district_id === selectedDistrictId,
  );
  const scopeLabel = selectedDistrict ? selectedDistrict.district_name : "全市";

  if (isLoading || !overview) {
    return (
      <Card className="flex h-full flex-col">
        <CardHeader>
          <p className="text-xs font-bold uppercase tracking-[0.16em] text-accent-slate">
            Core Metrics
          </p>
          <CardTitle className="text-lg font-bold text-slate-900">
            核心生育指標
          </CardTitle>
        </CardHeader>
        <CardContent className="flex flex-1 flex-col gap-2.5">
          {Array.from({ length: 4 }).map((_, index) => (
            <Skeleton key={index} className="h-16 w-full rounded-xl" />
          ))}
        </CardContent>
      </Card>
    );
  }

  const fertilityYears = [...overview.annual.fertility.years].sort(
    (a, b) => a.year_roc - b.year_roc,
  );
  const latestFertility = fertilityYears[fertilityYears.length - 1];
  const previousFertility = fertilityYears[fertilityYears.length - 2];

  const populationYears = [...overview.annual.population.years].sort(
    (a, b) => a.year_roc - b.year_roc,
  );
  const latestPopulation = populationYears[populationYears.length - 1];
  const previousPopulation = populationYears[populationYears.length - 2];

  function yoy(current: number, previous: number | undefined): number | null {
    if (previous === undefined || previous === 0) return null;
    return Math.round(((current - previous) / previous) * 1000) / 10;
  }

  const births = selectedDistrict
    ? latestFertility.districts.find((d) => d.district_id === selectedDistrict.district_id)
        ?.births_mother_age_18_35
    : latestFertility.city.births_mother_age_18_35;
  const prevBirths = selectedDistrict
    ? previousFertility?.districts.find((d) => d.district_id === selectedDistrict.district_id)
        ?.births_mother_age_18_35
    : previousFertility?.city.births_mother_age_18_35;

  const fertilityRate = selectedDistrict
    ? selectedDistrict.fertilityRate
    : latestFertility.city.fertility_rate;
  const prevFertilityRate = selectedDistrict
    ? previousFertility?.districts.find((d) => d.district_id === selectedDistrict.district_id)
        ?.fertility_rate
    : previousFertility?.city.fertility_rate;

  const youthShare = selectedDistrict
    ? latestPopulation.districts.find((d) => d.district_id === selectedDistrict.district_id)
        ?.youth_share_percent
    : latestPopulation.city.youth_share_percent;
  const prevYouthShare = selectedDistrict
    ? previousPopulation?.districts.find((d) => d.district_id === selectedDistrict.district_id)
        ?.youth_share_percent
    : previousPopulation?.city.youth_share_percent;

  const metrics: Metric[] = [
    {
      id: "total-births",
      icon: Baby,
      label: "青年總生育數",
      caption: "18–35 歲婦女年度生育數",
      value: births === undefined ? "資料待補" : formatInt(births),
      deltaPct: births !== undefined ? yoy(births, prevBirths) : null,
      avgDiffPct: null,
    },
    {
      id: "avg-fertility-rate",
      icon: HeartPulse,
      label: "育齡青年生育率",
      caption: "每千名 18–35 歲育齡人口之年度生育數",
      value: `${fertilityRate.toFixed(2)}‰`,
      deltaPct: yoy(fertilityRate, prevFertilityRate),
      avgDiffPct: selectedDistrict ? selectedDistrict.fertilityVsCityAvg - 100 : null,
      formula: FERTILITY_RATE_FORMULA,
    },
    {
      id: "youth-population-share",
      icon: Users,
      label: "青年人口占比",
      caption: "18–35 歲占該區總人口比例",
      value: youthShare === undefined ? "資料待補" : `${youthShare.toFixed(1)}%`,
      deltaPct: youthShare !== undefined ? yoy(youthShare, prevYouthShare) : null,
      avgDiffPct: null,
    },
  ];

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
        {metrics.map((metric) => {
          const Icon = metric.icon;
          const hasDelta = metric.deltaPct !== null;
          const isPositiveDelta = (metric.deltaPct ?? 0) >= 0;

          return (
            <div
              key={metric.id}
              className="flex flex-1 items-center gap-3 rounded-xl border border-slate-200 bg-slate-50 px-4 py-3"
            >
              <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
                <Icon className="h-4 w-4" aria-hidden="true" />
              </span>
              <div className="min-w-0 flex-1">
                <p className="flex items-center gap-1 text-xs font-semibold text-slate-600">
                  {metric.label}
                  {metric.formula ? (
                    <MetricInfoTooltip formula={metric.formula} />
                  ) : null}
                </p>
                <p className="mt-1 flex items-baseline gap-1.5">
                  <span className="text-2xl font-bold text-slate-900">
                    {metric.value}
                  </span>
                  {hasDelta ? (
                    <span
                      className={cn(
                        "text-xs font-bold",
                        isPositiveDelta ? "text-risk-high" : "text-risk-low",
                      )}
                    >
                      {formatSignedPercent(metric.deltaPct ?? 0)}
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
                  metric.avgDiffPct === null
                    ? "border-slate-200 bg-slate-100 text-slate-400"
                    : metric.avgDiffPct > 0
                      ? "border-risk-high/30 bg-risk-high/10 text-risk-high"
                      : metric.avgDiffPct < 0
                        ? "border-risk-low/30 bg-risk-low/10 text-risk-low"
                        : "border-slate-200 bg-slate-100 text-slate-400",
                )}
              >
                <span className="text-[9px] font-semibold uppercase tracking-wide opacity-70">
                  較平均
                </span>
                <span className="text-xs font-bold">
                  {metric.avgDiffPct === null
                    ? "－"
                    : formatSignedPercent(metric.avgDiffPct)}
                </span>
              </span>
            </div>
          );
        })}
        <p className="pt-1 text-[11px] text-slate-400">
          行內百分比為與去年同期相比，右側框框為與全市平均值相比（紅色代表較高、綠色代表較低）。托育資源覆蓋率待
          Backend 完成 geocoding 後補上，見 api_contract.md §7.2。
        </p>
      </CardContent>
    </Card>
  );
}
