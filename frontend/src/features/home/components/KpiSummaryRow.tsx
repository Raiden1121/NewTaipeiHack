import { motion } from "motion/react";
import { useDashboardOverview } from "@/lib/api/queries";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { formatInt, formatSignedPercent } from "@/lib/format";

export default function KpiSummaryRow() {
  const { data: overview, isLoading, isError, error, refetch } = useDashboardOverview();

  if (isLoading) {
    return (
      <div
        className="grid grid-cols-1 gap-4 sm:grid-cols-3"
        data-testid="kpi-skeleton"
      >
        {Array.from({ length: 3 }).map((_, index) => (
          <Skeleton key={index} className="h-32 w-full rounded-2xl" />
        ))}
      </div>
    );
  }

  if (isError || !overview) {
    const message =
      error instanceof Error ? error.message : "青年 KPI 資料載入失敗，請稍後再試。";

    return (
      <section
        role="alert"
        className="flex min-h-[140px] flex-col items-center justify-center gap-3 rounded-2xl border border-red-200 bg-red-50 p-8 text-center"
        data-testid="kpi-error"
      >
        <h2 className="text-lg font-bold text-red-700">KPI 資料載入失敗</h2>
        <p className="text-sm text-red-600">{message}</p>
        <Button variant="destructive" onClick={() => refetch()}>
          重新載入
        </Button>
      </section>
    );
  }

  const { kpis } = overview;
  const yoy = kpis.cityYouthPopulationYoY;

  const kpisView = [
    {
      label: "全台 18–35 歲青年人口",
      value: `${formatInt(kpis.nationalYouthPopulation)} 人`,
      detail:
        kpis.nationalYouthPopulationQuality === "proxy"
          ? "推估值（無全國官方統計 collector）"
          : `基準年 民國 ${kpis.referenceYearRoc} 年`,
    },
    {
      label: "新北市青年佔總人口比例",
      value: `${kpis.cityYouthPopulationShare.toFixed(1)}%`,
      detail: `新北市青年人口 ${formatInt(kpis.cityYouthPopulation)} 人`,
    },
    {
      label: "青年人口年增率 (YoY)",
      value: formatSignedPercent(yoy),
      detail: "較去年同期",
      valueClassName:
        yoy > 0 ? "text-risk-high" : yoy < 0 ? "text-risk-low" : undefined,
    },
  ];

  return (
    <div
      className="grid grid-cols-1 gap-4 sm:grid-cols-3"
      data-testid="kpi-success"
    >
      {kpisView.map((kpi, index) => (
        <motion.div
          key={kpi.label}
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: index * 0.08, duration: 0.35 }}
        >
          <Card>
            <CardHeader>
              <CardTitle className="text-sm font-semibold text-accent-slate">
                {kpi.label}
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p
                className={cn(
                  "text-2xl font-bold text-slate-900",
                  kpi.valueClassName,
                )}
              >
                {kpi.value}
              </p>
              <p className="mt-1 text-xs text-slate-500">{kpi.detail}</p>
            </CardContent>
          </Card>
        </motion.div>
      ))}
    </div>
  );
}
