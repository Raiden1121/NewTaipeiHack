import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
} from "react";
import { geoMercator, geoPath } from "d3-geo";
import { motion } from "motion/react";
import { Minus, Plus, RotateCcw } from "lucide-react";
import { useDistrictSummary } from "@/features/home/hooks/useDistrictSummary";
import {
  useNewTaipeiTopology,
  type DistrictFeature,
} from "@/hooks/useNewTaipeiTopology";
import { useSelectedDistrict } from "@/stores/useSelectedDistrict";
import { useSettingsStore } from "@/stores/useSettingsStore";
import { tieredFillColor, SELECTED_DISTRICT_FILL } from "@/lib/mapColors";
import { computeTercileThresholds } from "@/lib/quantile";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const MAP_WIDTH = 760;
const MAP_HEIGHT = 560;
// 讓投影範圍內縮，避免緊貼地圖邊界的行政區在選取／hover 加粗邊框時被 viewBox 裁切。
const MAP_PADDING = 14;
const MIN_SCALE = 1;
const MAX_SCALE = 4;
const SCALE_STEP = 1.6;
const CLICK_ZOOM_SCALE = 2.2;
const DRAG_THRESHOLD = 4;
// 允許地圖平移到僅剩一半在框內，確保邊緣行政區點選後也能置中。
const PAN_MARGIN_RATIO = 0.5;

const LEGEND_STEPS = ["bg-primary/20", "bg-primary/55", "bg-primary"];

interface View {
  scale: number;
  x: number;
  y: number;
}

const INITIAL_VIEW: View = { scale: 1, x: 0, y: 0 };

function clamp(value: number, min: number, max: number) {
  return Math.min(Math.max(value, min), max);
}

function clampView(view: View): View {
  const marginX = MAP_WIDTH * PAN_MARGIN_RATIO;
  const marginY = MAP_HEIGHT * PAN_MARGIN_RATIO;
  const minX = MAP_WIDTH - marginX - MAP_WIDTH * view.scale;
  const minY = MAP_HEIGHT - marginY - MAP_HEIGHT * view.scale;
  return {
    scale: view.scale,
    x: clamp(view.x, minX, marginX),
    y: clamp(view.y, minY, marginY),
  };
}

export default function ParticipationHotspotMap() {
  const svgRef = useRef<SVGSVGElement>(null);
  const dragState = useRef<{
    pointerId: number;
    startX: number;
    startY: number;
    originX: number;
    originY: number;
  } | null>(null);
  const movedRef = useRef(false);

  const [view, setView] = useState<View>(INITIAL_VIEW);
  const [animating, setAnimating] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const [hoveredDistrictId, setHoveredDistrictId] = useState<string | null>(null);
  const [pingKey, setPingKey] = useState(0);

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

  const selectedDistrictId = useSelectedDistrict(
    (state) => state.selectedDistrictId,
  );
  const selectDistrict = useSelectedDistrict((state) => state.selectDistrict);
  const colorTheme = useSettingsStore((state) => state.colorTheme);

  const districtById = useMemo(
    () => new Map(districts.map((district) => [district.district_id, district])),
    [districts],
  );

  const participationThresholds = useMemo(
    () =>
      computeTercileThresholds(
        districts.map((district) => district.youthCandidacyRatePer100k ?? 0),
      ),
    [districts],
  );

  const collection = useMemo(
    () => ({ type: "FeatureCollection" as const, features }),
    [features],
  );
  const projection = useMemo(
    () =>
      geoMercator().fitExtent(
        [
          [MAP_PADDING, MAP_PADDING],
          [MAP_WIDTH - MAP_PADDING, MAP_HEIGHT - MAP_PADDING],
        ],
        collection as never,
      ),
    [collection],
  );
  const pathGenerator = useMemo(() => geoPath(projection), [projection]);

  const selectedCentroid = useMemo(() => {
    if (!selectedDistrictId) return null;
    const feature = features.find(
      (item) => item.properties.id === selectedDistrictId,
    );
    if (!feature) return null;
    const [x, y] = pathGenerator.centroid(feature as never);
    return Number.isFinite(x) && Number.isFinite(y) ? { x, y } : null;
  }, [features, pathGenerator, selectedDistrictId]);

  const viewBoxUnitsPerPixel = useCallback(() => {
    const rect = svgRef.current?.getBoundingClientRect();
    return rect && rect.width > 0 ? MAP_WIDTH / rect.width : 1;
  }, []);

  // 觸控板兩指滑動 → 平移；不綁縮放（含 ctrlKey pinch）。以非被動監聽避免頁面捲動。
  useEffect(() => {
    const element = svgRef.current;
    if (!element) return;

    function handleWheel(event: WheelEvent) {
      event.preventDefault();
      const factor = viewBoxUnitsPerPixel();
      setAnimating(false);
      setView((prev) =>
        clampView({
          scale: prev.scale,
          x: prev.x - event.deltaX * factor,
          y: prev.y - event.deltaY * factor,
        }),
      );
    }

    element.addEventListener("wheel", handleWheel, { passive: false });
    return () => element.removeEventListener("wheel", handleWheel);
  }, [viewBoxUnitsPerPixel]);

  const zoomBy = useCallback((multiplier: number) => {
    setAnimating(true);
    setView((prev) => {
      const nextScale = clamp(prev.scale * multiplier, MIN_SCALE, MAX_SCALE);
      const centerX = MAP_WIDTH / 2;
      const centerY = MAP_HEIGHT / 2;
      const anchorX = (centerX - prev.x) / prev.scale;
      const anchorY = (centerY - prev.y) / prev.scale;
      return clampView({
        scale: nextScale,
        x: centerX - anchorX * nextScale,
        y: centerY - anchorY * nextScale,
      });
    });
  }, []);

  const resetView = useCallback(() => {
    setAnimating(true);
    setView(INITIAL_VIEW);
  }, []);

  const focusDistrict = useCallback(
    (feature: DistrictFeature) => {
      const [centroidX, centroidY] = pathGenerator.centroid(feature as never);
      if (!Number.isFinite(centroidX) || !Number.isFinite(centroidY)) return;
      setAnimating(true);
      setView((prev) => {
        const nextScale =
          prev.scale < CLICK_ZOOM_SCALE ? CLICK_ZOOM_SCALE : prev.scale;
        return clampView({
          scale: nextScale,
          x: MAP_WIDTH / 2 - centroidX * nextScale,
          y: MAP_HEIGHT / 2 - centroidY * nextScale,
        });
      });
    },
    [pathGenerator],
  );

  function handlePointerDown(event: ReactPointerEvent<SVGSVGElement>) {
    if (event.button !== 0) return;
    movedRef.current = false;
    dragState.current = {
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      originX: view.x,
      originY: view.y,
    };
    setAnimating(false);
  }

  function handlePointerMove(event: ReactPointerEvent<SVGSVGElement>) {
    const drag = dragState.current;
    if (!drag || drag.pointerId !== event.pointerId) return;
    const deltaX = event.clientX - drag.startX;
    const deltaY = event.clientY - drag.startY;
    if (!movedRef.current && Math.hypot(deltaX, deltaY) > DRAG_THRESHOLD) {
      movedRef.current = true;
      setIsDragging(true);
      svgRef.current?.setPointerCapture?.(drag.pointerId);
    }
    if (!movedRef.current) return;
    const factor = viewBoxUnitsPerPixel();
    setView(
      clampView({
        scale: view.scale,
        x: drag.originX + deltaX * factor,
        y: drag.originY + deltaY * factor,
      }),
    );
  }

  function endDrag(event: ReactPointerEvent<SVGSVGElement>) {
    const drag = dragState.current;
    if (!drag || drag.pointerId !== event.pointerId) return;
    if (svgRef.current?.hasPointerCapture?.(event.pointerId)) {
      svgRef.current.releasePointerCapture?.(event.pointerId);
    }
    dragState.current = null;
    setIsDragging(false);
  }

  // 選取行政區（不論來源為地圖點選或右側排名）→ 置中對應區域。
  const lastFocusedRef = useRef<string | null>(null);
  useEffect(() => {
    if (!selectedDistrictId) return;
    if (lastFocusedRef.current === selectedDistrictId) return;
    const feature = features.find(
      (item) => item.properties.id === selectedDistrictId,
    );
    if (!feature) return;
    lastFocusedRef.current = selectedDistrictId;
    const raf = requestAnimationFrame(() => focusDistrict(feature));
    return () => cancelAnimationFrame(raf);
  }, [selectedDistrictId, features, focusDistrict]);

  function handleDistrictClick(feature: DistrictFeature) {
    if (movedRef.current) return;
    selectDistrict(feature.properties.id);
    setPingKey((value) => value + 1);
  }

  const isLoading = topologyState === "loading" || isDistrictsLoading;
  const isError = topologyState === "error" || isDistrictsError;

  // 選取／hover 的行政區排到最後繪製，避免其加粗邊框被相鄰行政區蓋住而看似被裁切。
  const orderedFeatures =
    selectedDistrictId || hoveredDistrictId
      ? [
          ...features.filter(
            (item) =>
              item.properties.id !== selectedDistrictId &&
              item.properties.id !== hoveredDistrictId,
          ),
          ...features.filter(
            (item) =>
              item.properties.id === hoveredDistrictId &&
              item.properties.id !== selectedDistrictId,
          ),
          ...features.filter(
            (item) => item.properties.id === selectedDistrictId,
          ),
        ]
      : features;

  return (
    <Card className="h-full">
      <CardHeader>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.16em] text-accent-slate">
              Participation Map
            </p>
            <CardTitle className="text-lg font-bold text-slate-900">
              新北市青年參政指數分布
            </CardTitle>
          </div>
          <div className="flex items-center gap-1.5 text-[11px] font-semibold text-accent-slate">
            <span>低參政</span>
            {LEGEND_STEPS.map((step) => (
              <span
                key={step}
                className={`h-2.5 w-4 rounded-sm ${step}`}
                aria-hidden="true"
              />
            ))}
            <span>高參政</span>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <Skeleton className="h-[440px] w-full rounded-xl" />
        ) : isError ? (
          <section
            role="alert"
            className="flex min-h-[320px] flex-col items-center justify-center gap-3 rounded-xl border border-red-200 bg-red-50 p-8 text-center"
          >
            <h2 className="text-lg font-bold text-red-700">地圖資料載入失敗</h2>
            <p className="text-sm text-red-600">
              {topologyState === "error"
                ? topologyError ?? "地圖幾何資料載入失敗，請稍後再試。"
                : districtsError instanceof Error
                  ? districtsError.message
                  : "行政區資料載入失敗，請稍後再試。"}
            </p>
            <Button variant="destructive" onClick={() => refetch()}>
              重新載入
            </Button>
          </section>
        ) : (
          <div className="relative overflow-hidden rounded-xl border border-slate-200 bg-slate-50">
            <svg
              ref={svgRef}
              viewBox={`0 0 ${MAP_WIDTH} ${MAP_HEIGHT}`}
              role="img"
              aria-label="新北市 29 行政區青年參政指數互動地圖，可縮放、平移與點選行政區"
              className={cn(
                "block h-auto w-full touch-none select-none",
                isDragging ? "cursor-grabbing" : "cursor-grab",
              )}
              onPointerDown={handlePointerDown}
              onPointerMove={handlePointerMove}
              onPointerUp={endDrag}
              onPointerCancel={endDrag}
            >
              <g
                style={{
                  transform: `translate(${view.x}px, ${view.y}px) scale(${view.scale})`,
                  transformBox: "view-box",
                  transformOrigin: "0 0",
                  transition: animating
                    ? "transform 420ms cubic-bezier(0.4, 0, 0.2, 1)"
                    : "none",
                }}
                onTransitionEnd={() => setAnimating(false)}
              >
                {orderedFeatures.map((district) => {
                  const id = district.properties.id;
                  const name = district.properties.name ?? "未命名行政區";
                  const participationRate =
                    districtById.get(id)?.youthCandidacyRatePer100k;
                  const isSelected = id === selectedDistrictId;
                  const isHovered = id === hoveredDistrictId;

                  return (
                    <path
                      key={id}
                      d={pathGenerator(district as never) ?? undefined}
                      data-town-id={id}
                      aria-label={name}
                      className={cn(
                        "cursor-pointer transition-[filter] duration-150",
                        isSelected
                          ? "stroke-amber-700"
                          : isHovered
                            ? "stroke-amber-500 brightness-95"
                            : "stroke-white",
                      )}
                      style={{
                        fill: isSelected
                          ? SELECTED_DISTRICT_FILL
                          : tieredFillColor(participationRate, participationThresholds, colorTheme),
                        strokeWidth:
                          (isSelected || isHovered ? 3 : 1.5) / view.scale,
                      }}
                      onMouseEnter={() => setHoveredDistrictId(id)}
                      onMouseLeave={() => setHoveredDistrictId(null)}
                      onClick={() => handleDistrictClick(district)}
                    >
                      <title>{name}</title>
                    </path>
                  );
                })}

                {selectedCentroid && (
                  <motion.circle
                    key={`${selectedDistrictId}-${pingKey}`}
                    cx={selectedCentroid.x}
                    cy={selectedCentroid.y}
                    r={16 / view.scale}
                    strokeWidth={2.5 / view.scale}
                    className="pointer-events-none fill-none stroke-amber-500"
                    style={{ transformBox: "fill-box", transformOrigin: "center" }}
                    initial={{ scale: 0.4, opacity: 0.8 }}
                    animate={{ scale: 2.8, opacity: 0 }}
                    transition={{ duration: 0.75, ease: "easeOut" }}
                  />
                )}
              </g>
            </svg>

            <div className="absolute right-3 top-3 flex flex-col gap-1.5">
              <button
                type="button"
                onClick={() => zoomBy(SCALE_STEP)}
                disabled={view.scale >= MAX_SCALE}
                aria-label="放大"
                className="flex h-8 w-8 items-center justify-center rounded-md border border-slate-200 bg-white text-slate-600 shadow-sm transition-colors hover:bg-slate-50 disabled:opacity-40"
              >
                <Plus className="h-4 w-4" aria-hidden="true" />
              </button>
              <button
                type="button"
                onClick={() => zoomBy(1 / SCALE_STEP)}
                disabled={view.scale <= MIN_SCALE}
                aria-label="縮小"
                className="flex h-8 w-8 items-center justify-center rounded-md border border-slate-200 bg-white text-slate-600 shadow-sm transition-colors hover:bg-slate-50 disabled:opacity-40"
              >
                <Minus className="h-4 w-4" aria-hidden="true" />
              </button>
              <button
                type="button"
                onClick={resetView}
                disabled={view.scale === 1 && view.x === 0 && view.y === 0}
                aria-label="重設視圖"
                className="flex h-8 w-8 items-center justify-center rounded-md border border-slate-200 bg-white text-slate-600 shadow-sm transition-colors hover:bg-slate-50 disabled:opacity-40"
              >
                <RotateCcw className="h-4 w-4" aria-hidden="true" />
              </button>
            </div>

            <p className="pointer-events-none absolute bottom-2 left-3 text-[11px] font-medium text-slate-400">
              滾輪／觸控板滑動平移 · 拖曳移動 · ＋／− 縮放 · 點選行政區置中
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
