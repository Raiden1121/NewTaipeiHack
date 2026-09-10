import { useMemo, useState } from "react";
import { geoMercator, geoPath } from "d3-geo";
import { useDistrictSummary } from "../hooks/useDistrictSummary";
import { useNewTaipeiTopology } from "@/hooks/useNewTaipeiTopology";
import { useSelectedDistrict } from "@/stores/useSelectedDistrict";
import { opportunityFillColor, SELECTED_DISTRICT_FILL } from "@/lib/mapColors";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { RetentionRiskLevel } from "@/types/district";

const MAP_WIDTH = 760;
const MAP_HEIGHT = 560;

const LEGEND_STEPS = [
  "bg-primary/15",
  "bg-primary/40",
  "bg-primary/65",
  "bg-primary",
];

const RISK_LABEL: Record<RetentionRiskLevel, string> = {
  low: "低風險",
  medium: "中風險",
  high: "高風險",
};

const RISK_TEXT_CLASS: Record<RetentionRiskLevel, string> = {
  low: "text-risk-low",
  medium: "text-risk-medium",
  high: "text-risk-high",
};

export default function DistrictChoroplethMap() {
  const [hoveredDistrictId, setHoveredDistrictId] = useState<string | null>(
    null,
  );

  const {
    features,
    status: topologyState,
    error: topologyError,
  } = useNewTaipeiTopology();

  const {
    data: districts = [],
    isLoading: isDistrictsLoading,
    isError: isDistrictsError,
    error: districtsError,
    refetch,
  } = useDistrictSummary();

  const districtById = useMemo(() => {
    return new Map(districts.map((district) => [district.id, district]));
  }, [districts]);

  const collection = useMemo(
    () => ({ type: "FeatureCollection" as const, features }),
    [features],
  );
  const projection = useMemo(
    () => geoMercator().fitSize([MAP_WIDTH, MAP_HEIGHT], collection as never),
    [collection],
  );
  const pathGenerator = useMemo(() => geoPath(projection), [projection]);

  const selectedDistrictId = useSelectedDistrict(
    (state) => state.selectedDistrictId,
  );
  const selectDistrict = useSelectedDistrict((state) => state.selectDistrict);

  const isLoading = topologyState === "loading" || isDistrictsLoading;
  const isError = topologyState === "error" || isDistrictsError;

  if (isLoading) {
    return (
      <Skeleton
        className="h-[520px] w-full rounded-2xl"
        data-testid="map-skeleton"
      />
    );
  }

  if (isError) {
    const message =
      topologyState === "error"
        ? topologyError ?? "地圖幾何資料載入失敗，請稍後再試。"
        : districtsError instanceof Error
          ? districtsError.message
          : "行政區資料載入失敗，請稍後再試。";

    return (
      <section
        role="alert"
        className="flex min-h-[320px] flex-col items-center justify-center gap-3 rounded-2xl border border-red-200 bg-red-50 p-8 text-center"
        data-testid="map-error"
      >
        <h2 className="text-lg font-bold text-red-700">地圖資料載入失敗</h2>
        <p className="text-sm text-red-600">{message}</p>
        <Button variant="destructive" onClick={() => refetch()}>
          重新載入
        </Button>
      </section>
    );
  }

  // 常駐資訊面板：以 hover 為主，無 hover 時退回已選取行政區。
  const activeDistrictId = hoveredDistrictId ?? selectedDistrictId;
  const activeFeature = features.find(
    (item) => item.properties.id === activeDistrictId,
  );
  const activeSummary = activeDistrictId
    ? districtById.get(activeDistrictId)
    : undefined;

  // 已選取行政區排到最後繪製，讓上浮的整個塗層疊在其他區之上、邊界不被裁切。
  const orderedFeatures = selectedDistrictId
    ? [
        ...features.filter(
          (item) => item.properties.id !== selectedDistrictId,
        ),
        ...features.filter(
          (item) => item.properties.id === selectedDistrictId,
        ),
      ]
    : features;

  return (
    <section
      aria-labelledby="map-title"
      className="rounded-2xl border border-slate-200 bg-white p-7 shadow-sm"
    >
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="mb-1 text-xs font-bold uppercase tracking-[0.16em] text-accent-slate">
            Interactive Map
          </p>
          <h2 id="map-title" className="text-xl font-bold text-slate-900">
            29 區機會指數分布
          </h2>
        </div>
        <div className="flex items-center gap-1.5 text-[11px] font-semibold text-accent-slate">
          <span>低機會</span>
          {LEGEND_STEPS.map((step) => (
            <span
              key={step}
              className={cn("h-2.5 w-5 rounded-sm", step)}
              aria-hidden="true"
            />
          ))}
          <span>高機會</span>
        </div>
      </div>

      <div className="relative overflow-hidden rounded-xl border border-slate-200 bg-slate-50">
        <svg
          viewBox={`0 0 ${MAP_WIDTH} ${MAP_HEIGHT}`}
          role="img"
          aria-label="新北市 29 行政區機會指數互動地圖"
          className="block h-auto w-full"
        >
          <g>
            {orderedFeatures.map((district) => {
              const id = district.properties.id;
              const name = district.properties.name ?? "未命名行政區";
              const opportunityIndex = districtById.get(id)?.opportunityIndex;
              const isSelected = id === selectedDistrictId;
              const isHovered = id === hoveredDistrictId;

              return (
                <path
                  key={id}
                  d={pathGenerator(district as never) ?? undefined}
                  data-town-id={id}
                  aria-label={name}
                  className={cn(
                    "cursor-pointer stroke-white stroke-[1.5] transition-[filter,stroke-width,transform] duration-200",
                    isHovered && "stroke-[3] stroke-amber-500 brightness-95",
                    isSelected && "stroke-[3] stroke-amber-700",
                  )}
                  style={{
                    fill: isSelected
                      ? SELECTED_DISTRICT_FILL
                      : opportunityFillColor(opportunityIndex),
                    transformBox: "fill-box",
                    transformOrigin: "center",
                    transform: isSelected ? "translateY(-8px)" : undefined,
                    filter: isSelected
                      ? "drop-shadow(0 8px 10px rgba(16, 35, 63, 0.35))"
                      : undefined,
                  }}
                  onMouseEnter={() => setHoveredDistrictId(id)}
                  onMouseLeave={() => setHoveredDistrictId(null)}
                  onClick={() => selectDistrict(id)}
                >
                  <title>{name}</title>
                </path>
              );
            })}
          </g>
        </svg>

        <div className="pointer-events-none absolute right-3 top-3 w-44 rounded-xl border border-slate-200 bg-white/95 p-3 shadow-sm backdrop-blur">
          {activeFeature ? (
            <>
              <p className="text-sm font-bold text-slate-900">
                {activeFeature.properties.name}
              </p>
              <dl className="mt-2 space-y-1.5 text-xs">
                <div className="flex items-center justify-between">
                  <dt className="text-accent-slate">機會指數</dt>
                  <dd className="font-bold text-slate-900">
                    {activeSummary ? activeSummary.opportunityIndex : "—"}
                  </dd>
                </div>
                <div className="flex items-center justify-between">
                  <dt className="text-accent-slate">留才風險</dt>
                  <dd
                    className={cn(
                      "font-bold",
                      activeSummary
                        ? RISK_TEXT_CLASS[activeSummary.retentionRiskLevel]
                        : "text-slate-400",
                    )}
                  >
                    {activeSummary
                      ? RISK_LABEL[activeSummary.retentionRiskLevel]
                      : "—"}
                  </dd>
                </div>
              </dl>
            </>
          ) : (
            <p className="text-xs leading-relaxed text-slate-400">
              將游標移至地圖，或點選行政區查看各區指數
            </p>
          )}
        </div>
      </div>
    </section>
  );
}
