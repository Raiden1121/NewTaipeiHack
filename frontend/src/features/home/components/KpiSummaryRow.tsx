import { motion } from "motion/react";
import { useDistrictSummary } from "../hooks/useDistrictSummary";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { DistrictSummary, RetentionRiskLevel } from "@/types/district";

const NATIONAL_YOUTH_POPULATION = 4_820_000;
const NATIONAL_YOUTH_POPULATION_SHARE = 20.6;
const CITY_YOUTH_POPULATION_SHARE = 28.4;
const YOUTH_POPULATION_YOY = -1.2;

const RISK_LABEL: Record<RetentionRiskLevel, string> = {
  low: "低風險",
  medium: "中風險",
  high: "高風險",
};

function averageRetentionRisk(
  districts: DistrictSummary[],
): RetentionRiskLevel {
  const counts: Record<RetentionRiskLevel, number> = {
    low: 0,
    medium: 0,
    high: 0,
  };
  districts.forEach((district) => {
    counts[district.retentionRiskLevel] += 1;
  });

  return (Object.keys(counts) as RetentionRiskLevel[]).reduce(
    (mostCommon, level) =>
      counts[level] > counts[mostCommon] ? level : mostCommon,
    "low" as RetentionRiskLevel,
  );
}

function formatNumber(value: number) {
  return new Intl.NumberFormat("zh-Hant-TW").format(Math.round(value));
}

export default function KpiSummaryRow() {
  const {
    data: districts = [],
    isLoading,
    isError,
    error,
    refetch,
  } = useDistrictSummary();

  if (isLoading) {
    return (
      <div
        className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4"
        data-testid="kpi-skeleton"
      >
        {Array.from({ length: 4 }).map((_, index) => (
          <Skeleton key={index} className="h-32 w-full rounded-2xl" />
        ))}
      </div>
    );
  }

  if (isError) {
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

  const cityYouthPopulation = districts.reduce(
    (total, district) => total + district.youthPopulation,
    0,
  );
  const riskLevel = averageRetentionRisk(districts);

  const kpis = [
    {
      label: "全台 18–35 歲青年人口",
      value: `${formatNumber(NATIONAL_YOUTH_POPULATION)} 人`,
      detail: `全台佔比 ${NATIONAL_YOUTH_POPULATION_SHARE}%`,
    },
    {
      label: "新北市青年佔總人口比例",
      value: `${CITY_YOUTH_POPULATION_SHARE}%`,
      detail: `新北市青年人口 ${formatNumber(cityYouthPopulation)} 人`,
    },
    {
      label: "青年人口年增率 (YoY)",
      value: `${YOUTH_POPULATION_YOY > 0 ? "+" : ""}${YOUTH_POPULATION_YOY}%`,
      detail: "較去年同期",
    },
  ];

  return (
    <div
      className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4"
      data-testid="kpi-success"
    >
      {kpis.map((kpi, index) => (
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
              <p className="text-2xl font-bold text-slate-900">{kpi.value}</p>
              <p className="mt-1 text-xs text-slate-500">{kpi.detail}</p>
            </CardContent>
          </Card>
        </motion.div>
      ))}
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.24, duration: 0.35 }}
      >
        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-semibold text-accent-slate">
              平均留才風險等級
            </CardTitle>
          </CardHeader>
          <CardContent>
            <Badge variant={riskLevel}>{RISK_LABEL[riskLevel]}</Badge>
          </CardContent>
        </Card>
      </motion.div>
    </div>
  );
}
