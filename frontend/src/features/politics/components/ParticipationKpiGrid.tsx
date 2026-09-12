import { motion } from "motion/react";
import { Building2, Gauge, Target } from "lucide-react";
import { useDistrictSummary } from "@/features/home/hooks/useDistrictSummary";
import { useDashboardOverview } from "@/lib/api/queries";
import { useSelectedDistrict } from "@/stores/useSelectedDistrict";
import { Card, CardContent } from "@/components/ui/card";

export default function ParticipationKpiGrid() {
  const { data: districts = [] } = useDistrictSummary();
  const { data: overview } = useDashboardOverview();
  const selectedDistrictId = useSelectedDistrict(
    (state) => state.selectedDistrictId,
  );

  const selectedDistrict = districts.find(
    (district) => district.district_id === selectedDistrictId,
  );

  const scopeLabel = selectedDistrict ? selectedDistrict.district_name : "全市";
  const serviceCoverageValue = selectedDistrict
    ? selectedDistrict.serviceCoverageRate
    : (overview?.service_coverage.value ?? null);

  // 青年里長占比：選取行政區時用該區的收斂值；未選取時用全市加總（皆固定為民國 111 年屆，
  // 見 api_contract.md §6.2——這是唯一有完整人口分母可用的一屆）。
  const boroughChiefRatio = selectedDistrict
    ? selectedDistrict.youthBoroughChiefRatioPercent
    : (overview?.elections.borough_chief_v1_citywide.ratio_percent ?? null);

  const kpis = [
    {
      id: "service-coverage",
      icon: Target,
      label: "服務涵蓋率",
      caption: "據點服務覆蓋之青年人口",
      value: serviceCoverageValue === null ? "資料待補" : `${serviceCoverageValue.toFixed(1)}%`,
    },
    {
      id: "youth-borough-chief",
      icon: Building2,
      label: "青年里長占比",
      caption: "青年當選里長之比例（民國 111 年屆）",
      value: boroughChiefRatio === null ? "資料待補" : `${boroughChiefRatio.toFixed(1)}%`,
    },
    {
      id: "yrr",
      icon: Gauge,
      label: "YRR (Youth Rep. Ratio)",
      caption: "席次與青年人口占比之比值",
      value: "資料待補",
    },
  ];

  return (
    <div className="flex flex-col gap-3">
      <p className="text-xs font-semibold text-accent-slate">
        目前檢視範圍：
        <span className="font-bold text-slate-700">{scopeLabel}</span>
        {selectedDistrict ? "（點選地圖或右側排名切換）" : "（點選地圖選擇行政區）"}
      </p>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {kpis.map((kpi, index) => {
          const Icon = kpi.icon;
          return (
            <motion.div
              key={kpi.id}
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: index * 0.05, duration: 0.3 }}
            >
              <Card className="h-full">
                <CardContent className="flex items-start justify-between gap-3 p-5">
                  <div>
                    <p className="text-sm font-semibold text-slate-600">
                      {kpi.label}
                    </p>
                    <p className="mt-1 text-3xl font-bold text-slate-900">
                      {kpi.value}
                    </p>
                    <p className="mt-1 text-xs text-slate-400">
                      {kpi.caption}
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
        青年里長占比僅民國 111 年屆有完整資料；YRR 缺選舉人年齡結構資料源，待補，見
        api_contract.md §6.2。
      </p>
    </div>
  );
}
