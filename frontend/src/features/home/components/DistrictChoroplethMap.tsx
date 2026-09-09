import { useMemo, useState } from "react";
import { geoMercator, geoPath } from "d3-geo";
import { useDistrictSummary } from "../hooks/useDistrictSummary";
import { useNewTaipeiTopology } from "@/hooks/useNewTaipeiTopology";
import { useSelectedDistrict } from "@/stores/useSelectedDistrict";
import { opportunityFillColor, SELECTED_DISTRICT_FILL } from "@/lib/mapColors";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const MAP_WIDTH = 760;
const MAP_HEIGHT = 560;

function clamp(value: number, min: number, max: number) {
  return Math.min(Math.max(value, min), max);
}

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

  const hoveredDistrict = features.find(
    (item) => item.properties.id === hoveredDistrictId,
  );
  const tooltipPoint = hoveredDistrict
    ? pathGenerator.centroid(hoveredDistrict as never)
    : null;
  const tooltipX = tooltipPoint
    ? clamp(tooltipPoint[0] - 54, 12, MAP_WIDTH - 132)
    : 0;
  const tooltipY = tooltipPoint
    ? clamp(tooltipPoint[1] - 42, 12, MAP_HEIGHT - 48)
    : 0;

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

  return (
    <section
      aria-labelledby="map-title"
      className="rounded-2xl border border-slate-200 bg-white p-7 shadow-sm"
    >
      <div className="mb-4 flex items-start justify-between gap-4">
        <div>
          <p className="mb-1 text-xs font-bold uppercase tracking-[0.16em] text-accent-slate">
            Interactive Map
          </p>
          <h2 id="map-title" className="text-xl font-bold text-slate-900">
            29 區機會指數分布
          </h2>
        </div>
        <span className="rounded-full bg-slate-100 px-3 py-1.5 text-xs font-bold uppercase text-slate-500">
          Hover / Click
        </span>
      </div>

      <div className="relative overflow-hidden rounded-xl border border-slate-200 bg-slate-50">
        <svg
          viewBox={`0 0 ${MAP_WIDTH} ${MAP_HEIGHT}`}
          role="img"
          aria-label="新北市 29 行政區機會指數互動地圖"
          className="block h-auto w-full"
        >
          <g>
            {features.map((district) => {
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
                    "cursor-pointer stroke-white stroke-[1.5] transition-[filter,stroke-width] duration-150",
                    isHovered && "stroke-[3] stroke-amber-500 brightness-95",
                    isSelected && "stroke-[3] stroke-amber-700",
                  )}
                  style={{
                    fill: isSelected
                      ? SELECTED_DISTRICT_FILL
                      : opportunityFillColor(opportunityIndex),
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
          {hoveredDistrict && tooltipPoint && (
            <g
              pointerEvents="none"
              transform={`translate(${tooltipX} ${tooltipY})`}
            >
              <rect width="132" height="36" rx="9" fill="#10233f" />
              <text
                x="66"
                y="23"
                textAnchor="middle"
                fill="#ffffff"
                fontSize="14"
                fontWeight="700"
              >
                {hoveredDistrict.properties.name}
              </text>
            </g>
          )}
        </svg>
      </div>
    </section>
  );
}
