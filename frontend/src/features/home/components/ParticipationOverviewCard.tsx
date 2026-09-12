import { AlertCircle } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useDashboardOverview } from "@/lib/api/queries";
import { formatOrFallback } from "@/lib/format";
import MetricInfoTooltip from "@/components/shared/MetricInfoTooltip";
import {
  SERVICE_COVERAGE_FORMULA,
  YOUTH_CANDIDACY_RATE_FORMULA,
} from "@/lib/metricFormulas";

export default function ParticipationOverviewCard() {
  const { data: overview, isLoading } = useDashboardOverview();

  if (isLoading || !overview) {
    return (
      <Card className="h-full">
        <CardHeader>
          <p className="text-xs font-bold uppercase tracking-[0.16em] text-accent-slate">
            Civic Participation
          </p>
          <CardTitle className="text-lg font-bold text-slate-900">
            青年參政概況
          </CardTitle>
        </CardHeader>
        <CardContent>
          <Skeleton className="h-16 w-full rounded-xl" />
        </CardContent>
      </Card>
    );
  }

  const latestCandidacy = [...overview.elections.city_councilor_t1_citywide]
    .filter((year) => year.quality_status === "observed")
    .sort((a, b) => b.year_roc - a.year_roc)[0];

  const serviceCoverage = overview.service_coverage;

  return (
    <Card className="h-full">
      <CardHeader>
        <p className="text-xs font-bold uppercase tracking-[0.16em] text-accent-slate">
          Civic Participation
        </p>
        <CardTitle className="text-lg font-bold text-slate-900">
          青年參政概況
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-2 gap-3">
          <div className="rounded-xl bg-slate-50 p-3">
            <p className="flex items-center gap-1 text-xs font-semibold text-accent-slate">
              市議員青年參選率
              <MetricInfoTooltip formula={YOUTH_CANDIDACY_RATE_FORMULA} />
            </p>
            <div className="mt-1 flex items-end gap-1.5">
              <span className="text-2xl font-bold text-primary">
                {formatOrFallback(latestCandidacy?.youth_candidacy_rate, (v) => v.toFixed(2))}
              </span>
              <span className="mb-1 text-xs font-semibold text-accent-slate">
                每十萬青年
              </span>
            </div>
            <p className="mt-1 text-[11px] text-slate-400">
              民國 {latestCandidacy?.year_roc ?? "—"} 年，僅此屆有完整人口分母可計算
            </p>
          </div>
          <div className="rounded-xl bg-slate-50 p-3">
            <p className="flex items-center gap-1 text-xs font-semibold text-accent-slate">
              整體服務涵蓋率
              <MetricInfoTooltip formula={SERVICE_COVERAGE_FORMULA} />
            </p>
            <p className="mt-1 text-2xl font-bold text-slate-900">
              {serviceCoverage.value.toFixed(1)}%
            </p>
            {serviceCoverage.status === "partial" && (
              <p className="mt-1 flex items-center gap-1 text-[11px] text-accent-warning">
                <AlertCircle className="h-3 w-3" aria-hidden="true" />
                資料涵蓋不足（僅 {serviceCoverage.verified_point_count} 個據點）
              </p>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
