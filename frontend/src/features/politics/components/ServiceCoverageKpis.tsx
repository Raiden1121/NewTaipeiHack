import { motion } from "motion/react";
import { Target, MapPinOff, Scale } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";

interface CoverageKpi {
  id: string;
  label: string;
  value: string;
  caption: string;
  icon: LucideIcon;
}

// 佔位資料，待 Backend API 提供整理後結果。
const KPIS: CoverageKpi[] = [
  {
    id: "coverage",
    label: "服務涵蓋率",
    value: "68%",
    caption: "據點服務覆蓋之青年人口",
    icon: Target,
  },
  {
    id: "desert",
    label: "服務荒漠指數",
    value: "2.4",
    caption: "高青年人口但據點稀疏之評分",
    icon: MapPinOff,
  },
  {
    id: "mismatch",
    label: "供需錯配",
    value: "15 區",
    caption: "人口與據點數排名錯位之行政區",
    icon: Scale,
  },
];

export default function ServiceCoverageKpis() {
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
      {KPIS.map((kpi, index) => {
        const Icon = kpi.icon;
        return (
          <motion.div
            key={kpi.id}
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: index * 0.06, duration: 0.3 }}
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
                  <p className="mt-1 text-xs text-slate-400">{kpi.caption}</p>
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
  );
}
