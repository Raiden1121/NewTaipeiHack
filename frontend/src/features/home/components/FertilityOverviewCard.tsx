import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useDashboardOverview } from "@/lib/api/queries";
import { formatSignedPercent } from "@/lib/format";
import MetricInfoTooltip from "@/components/shared/MetricInfoTooltip";
import { FERTILITY_RATE_FORMULA } from "@/lib/metricFormulas";

export default function FertilityOverviewCard() {
  const { data: overview, isLoading } = useDashboardOverview();

  if (isLoading || !overview) {
    return (
      <Card className="h-full">
        <CardHeader>
          <p className="text-xs font-bold uppercase tracking-[0.16em] text-accent-slate">
            Fertility & Family
          </p>
          <CardTitle className="text-lg font-bold text-slate-900">
            青年生育與成家
          </CardTitle>
        </CardHeader>
        <CardContent>
          <Skeleton className="h-16 w-full rounded-xl" />
        </CardContent>
      </Card>
    );
  }

  const years = [...overview.annual.fertility.years].sort((a, b) => a.year_roc - b.year_roc);
  const latest = years[years.length - 1];
  const previous = years[years.length - 2];
  const yoy =
    previous && previous.city.fertility_rate !== 0
      ? ((latest.city.fertility_rate - previous.city.fertility_rate) / previous.city.fertility_rate) *
        100
      : null;

  return (
    <Card className="h-full">
      <CardHeader>
        <p className="text-xs font-bold uppercase tracking-[0.16em] text-accent-slate">
          Fertility & Family
        </p>
        <CardTitle className="text-lg font-bold text-slate-900">
          青年生育與成家
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-2 gap-3">
          <div className="rounded-xl bg-slate-50 p-3">
            <p className="flex items-center gap-1 text-xs font-semibold text-accent-slate">
              平均生育率
              <MetricInfoTooltip formula={FERTILITY_RATE_FORMULA} />
            </p>
            <p className="mt-1 text-2xl font-bold text-slate-900">
              {latest.city.fertility_rate.toFixed(2)}
              <span className="text-sm font-semibold">‰</span>
            </p>
          </div>
          <div className="rounded-xl bg-slate-50 p-3">
            <p className="text-xs font-semibold text-accent-slate">較去年</p>
            <p
              className={
                yoy === null
                  ? "mt-1 text-2xl font-bold text-slate-400"
                  : `mt-1 text-2xl font-bold ${yoy >= 0 ? "text-risk-high" : "text-risk-low"}`
              }
            >
              {yoy === null ? "—" : formatSignedPercent(yoy)}
            </p>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
