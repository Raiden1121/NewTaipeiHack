import { motion } from "motion/react";
import { BarChart3, MapPin } from "lucide-react";
import { useDistrictSummary } from "@/features/home/hooks/useDistrictSummary";
import { useSelectedDistrict } from "@/stores/useSelectedDistrict";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { YoiComponents } from "@/lib/api/types";
import MetricInfoTooltip from "@/components/shared/MetricInfoTooltip";
import { OPPORTUNITY_INDEX_FORMULA } from "@/lib/metricFormulas";

interface DimensionScore {
  label: string;
  value: number;
}

const SIZE = 240;
const CENTER = SIZE / 2;
const RADIUS = 74;
const LABEL_RATIO = 1.2;
const GRID_LEVELS = [0.25, 0.5, 0.75, 1];

// 五個頂點順序固定：工作機會 → 薪資水準 → 人才資源 → 居住友善度 → 交通可及（順時針），
// 見 api_contract.md §5.2。housing 分數方向已是「越高越好」，不得再反轉。
function toDimensions(components: YoiComponents): DimensionScore[] {
  return [
    { label: "工作機會", value: components.job },
    { label: "薪資水準", value: components.salary },
    { label: "人才資源", value: components.talent },
    { label: "居住友善度", value: components.housing },
    { label: "交通可及", value: components.transport },
  ];
}

function labelBaseline(sin: number): "auto" | "hanging" | "middle" {
  if (sin < -0.5) return "auto";
  if (sin > 0.5) return "hanging";
  return "middle";
}

function polarPoint(index: number, count: number, ratio: number) {
  const angle = (Math.PI * 2 * index) / count - Math.PI / 2;
  return {
    x: CENTER + Math.cos(angle) * RADIUS * ratio,
    y: CENTER + Math.sin(angle) * RADIUS * ratio,
  };
}

function polygonPoints(ratios: number[]) {
  return ratios
    .map((ratio, index) => {
      const { x, y } = polarPoint(index, ratios.length, ratio);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
}

export default function DistrictDetailCard() {
  const selectedDistrictId = useSelectedDistrict(
    (state) => state.selectedDistrictId,
  );
  const { data: districts = [] } = useDistrictSummary();

  const selectedDistrict = districts.find(
    (district) => district.district_id === selectedDistrictId,
  );

  if (!selectedDistrict) {
    return (
      <Card className="flex h-full flex-col">
        <CardHeader>
          <p className="text-xs font-bold uppercase tracking-[0.16em] text-accent-slate">
            District Detail
          </p>
          <CardTitle className="text-lg font-bold text-slate-900">
            行政區詳細分析
          </CardTitle>
        </CardHeader>
        <CardContent className="flex flex-1 flex-col items-center justify-center gap-2 text-center">
          <MapPin className="h-8 w-8 text-slate-300" aria-hidden="true" />
          <p className="text-sm font-semibold text-slate-500">
            點選左側地圖選擇行政區
          </p>
          <p className="text-xs text-slate-400">
            選定後顯示該區青年機會指數細項
          </p>
        </CardContent>
      </Card>
    );
  }

  const dimensions = toDimensions(selectedDistrict.yoiComponents);
  const dataPoints = polygonPoints(dimensions.map((item) => item.value / 100));

  return (
    <Card className="flex h-full flex-col">
      <CardHeader>
        <div className="flex items-start justify-between gap-2">
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.16em] text-accent-slate">
              District Detail
            </p>
            <CardTitle className="flex items-center gap-2 text-lg font-bold text-slate-900">
              <BarChart3 className="h-5 w-5 text-primary" aria-hidden="true" />
              {selectedDistrict.district_name} 詳細分析
            </CardTitle>
          </div>
          <div className="text-right">
            <p className="flex items-center justify-end gap-1 text-xs font-semibold text-accent-slate">
              綜合分數
              <MetricInfoTooltip formula={OPPORTUNITY_INDEX_FORMULA} />
            </p>
            <p className="text-3xl font-bold text-primary">
              {selectedDistrict.opportunityIndex.toFixed(1)}
            </p>
          </div>
        </div>
      </CardHeader>
      <CardContent className="flex flex-1 flex-col gap-4">
        <div className="flex justify-center">
          <svg
            viewBox={`0 0 ${SIZE} ${SIZE}`}
            className="h-52 w-52"
            role="img"
            aria-label={`${selectedDistrict.district_name}五維度雷達圖：${dimensions.map((d) => `${d.label} ${d.value}`).join("、")}`}
          >
            {GRID_LEVELS.map((level, index) => (
              <motion.polygon
                key={`${selectedDistrict.district_id}-grid-${level}`}
                points={polygonPoints(dimensions.map(() => level))}
                className="fill-none stroke-slate-200"
                strokeWidth={1}
                style={{ transformBox: "view-box", transformOrigin: "100px 100px" }}
                initial={{ scale: 0, opacity: 0 }}
                animate={{ scale: 1, opacity: 1 }}
                transition={{ delay: index * 0.05, duration: 0.3 }}
              />
            ))}
            {dimensions.map((dimension, index) => {
              const { x, y } = polarPoint(index, dimensions.length, 1);
              return (
                <line
                  key={dimension.label}
                  x1={CENTER}
                  y1={CENTER}
                  x2={x}
                  y2={y}
                  className="stroke-slate-200"
                  strokeWidth={1}
                />
              );
            })}
            {dimensions.map((dimension, index) => {
              const angle =
                (Math.PI * 2 * index) / dimensions.length - Math.PI / 2;
              const { x, y } = polarPoint(index, dimensions.length, LABEL_RATIO);
              return (
                <text
                  key={`${dimension.label}-label`}
                  x={x}
                  y={y}
                  textAnchor="middle"
                  dominantBaseline={labelBaseline(Math.sin(angle))}
                  className="fill-slate-500"
                  fontSize={11}
                  fontWeight={600}
                >
                  {dimension.label}
                </text>
              );
            })}
            <motion.polygon
              key={`${selectedDistrict.district_id}-data`}
              points={dataPoints}
              className="fill-primary stroke-primary"
              fillOpacity={0.2}
              strokeWidth={2}
              strokeLinejoin="round"
              style={{ transformBox: "view-box", transformOrigin: "100px 100px" }}
              initial={{ scale: 0, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              transition={{ type: "spring", stiffness: 130, damping: 14, delay: 0.1 }}
            />
            {dimensions.map((dimension, index) => {
              const { x, y } = polarPoint(
                index,
                dimensions.length,
                dimension.value / 100,
              );
              return (
                <motion.circle
                  key={`${selectedDistrict.district_id}-dot-${dimension.label}`}
                  cx={x}
                  cy={y}
                  r={3}
                  className="fill-primary"
                  style={{ transformBox: "fill-box", transformOrigin: "center" }}
                  initial={{ scale: 0, opacity: 0 }}
                  animate={{ scale: 1, opacity: 1 }}
                  transition={{ delay: 0.25 + index * 0.05, duration: 0.25 }}
                />
              );
            })}
          </svg>
        </div>
        <ul className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
          {dimensions.map((dimension) => (
            <li
              key={dimension.label}
              className="flex items-center justify-between border-b border-slate-100 pb-1.5"
            >
              <span className="text-slate-600">{dimension.label}</span>
              <span className="font-bold text-slate-900">{dimension.value.toFixed(1)}</span>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}
