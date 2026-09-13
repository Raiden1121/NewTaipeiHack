import { useMemo, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { useYouthKeywordFrequency } from "@/lib/api/queries";
import type { YouthKeyword, YouthKeywordFrequencyAnalysis } from "@/lib/api/types";
import { cn } from "@/lib/utils";

function clamp(value: number, min: number, max: number) {
  return Math.min(Math.max(value, min), max);
}

// 字級縮小、字重降低：懷疑被切到是粗體大字在瀏覽器算合成粗體（synthetic bold）
// 時，實際筆畫寬度比字型量測值更寬所致，先用較小字級＋較輕字重降低風險，
// 待之後有瀏覽器可實測時再回頭精修。
const FONT_SIZE: Record<number, number> = {
  5: 80,
  4: 70,
  3: 60,
  2: 50,
  1: 45,
};

function fontWeightFor(weight: number) {
  return weight >= 4 ? 700 : weight >= 3 ? 600 : 500;
}

// 僅使用 tailwind theme token 對應的 fill 類別（不寫死色碼）。
const FILL_PALETTE = [
  "fill-primary",
  "fill-accent-teal",
  "fill-accent-warning",
  "fill-risk-high",
  "fill-risk-medium",
  "fill-slate-700",
  "fill-slate-400",
];

function seededUnit(seed: number): number {
  const x = Math.sin(seed * 127.1 + 311.7) * 43758.5453;
  return x - Math.floor(x);
}

interface PlacedWord {
  label: string;
  x: number;
  y: number;
  fontSize: number;
  weight: number;
  rotate: number;
  fill: string;
  termFrequency: number;
  boxW: number;
  boxH: number;
}

interface Box {
  x: number;
  y: number;
  w: number;
  h: number;
}

interface ViewBoxBounds {
  minX: number;
  minY: number;
  width: number;
  height: number;
}

// 詞與詞之間額外保留的間距。
const WORD_GAP = 14;

// 曾嘗試用 getBBox() 量測瀏覽器實際渲染出的字寬字高取代估算值，
// 但在實測環境下反而更不穩定（懷疑跟量測時機／隱藏容器有關，未能在此環境定位根因）。
// 改回單純估算，但大幅放寬安全係數，寧可留白多一點也不要有任何重疊或被裁切的風險：
// 寬度用 1.4 倍字寬 + 較大固定內距，高度同樣加大，外加 14px 額外間距緩衝。
function estimateTextBox(term: string, fontSize: number) {
  return {
    width: term.length * fontSize * 1.4 + 24,
    height: fontSize * 1.5 + 16,
  };
}

// 依重要程度由大到小，沿螺旋外擴尋找不與既有詞碰撞的位置（AABB 碰撞偵測）。
function layoutWordCloud(keywords: YouthKeyword[]): {
  placed: PlacedWord[];
  bounds: ViewBoxBounds;
} {
  const sorted = [...keywords].sort((a, b) => b.weight - a.weight);
  const boxes: Box[] = [];
  const placed: PlacedWord[] = [];

  sorted.forEach((keyword, index) => {
    const fontSize = FONT_SIZE[keyword.weight] ?? FONT_SIZE[1];
    const vertical = seededUnit(index * 3 + 1) > 0.88;
    const { width: textW, height: textH } = estimateTextBox(keyword.term, fontSize);
    const w = vertical ? textH : textW;
    const h = vertical ? textW : textH;

    let angle = seededUnit(index + 1) * Math.PI * 2;
    let radius = 0;
    let x = 0;
    let y = 0;
    let placedSafely = false;

    for (let iter = 0; iter < 20000; iter += 1) {
      x = Math.cos(angle) * radius;
      y = Math.sin(angle) * radius * 0.6;
      const hit = boxes.some(
        (b) =>
          Math.abs(b.x - x) * 2 < b.w + w + WORD_GAP * 2 &&
          Math.abs(b.y - y) * 2 < b.h + h + WORD_GAP * 2,
      );
      if (!hit) {
        placedSafely = true;
        break;
      }
      angle += 0.18;
      radius += 0.6;
    }

    // 理論上 20000 步、半徑可達數千單位，不該發生找不到空位；萬一真的發生，
    // 寧可把詞硬塞到目前群集最外緣正右方，也不要用最後一次仍相撞的座標。
    if (!placedSafely) {
      const farRight = boxes.length > 0 ? Math.max(...boxes.map((b) => b.x + b.w / 2)) : 0;
      x = farRight + w / 2 + WORD_GAP * 2;
      y = 0;
    }

    boxes.push({ x, y, w, h });
    placed.push({
      label: keyword.term,
      x,
      y,
      fontSize,
      weight: keyword.weight,
      rotate: vertical ? -90 : 0,
      fill: FILL_PALETTE[index % FILL_PALETTE.length],
      termFrequency: keyword.term_frequency,
      boxW: w,
      boxH: h,
    });
  });

  const pad = 10;
  const minX = Math.min(...boxes.map((b) => b.x - b.w / 2)) - pad;
  const maxX = Math.max(...boxes.map((b) => b.x + b.w / 2)) + pad;
  const minY = Math.min(...boxes.map((b) => b.y - b.h / 2)) - pad;
  const maxY = Math.max(...boxes.map((b) => b.y + b.h / 2)) + pad;

  return {
    placed,
    bounds: { minX, minY, width: maxX - minX, height: maxY - minY },
  };
}

// source_periods 是 dataset -> 民國年清單；文字雲是全期間合併，只顯示涵蓋的年度範圍。
function coveredYearRange(sourcePeriods: YouthKeywordFrequencyAnalysis["source_periods"] | undefined): string | null {
  const years = Object.values(sourcePeriods ?? {})
    .flat()
    .map(Number)
    .filter(Number.isFinite);
  if (years.length === 0) return null;
  const min = Math.min(...years);
  const max = Math.max(...years);
  return min === max ? `${min}` : `${min}–${max}`;
}

export default function YouthTopicWordCloud() {
  const { data: analysis, isLoading, isError, error, refetch } = useYouthKeywordFrequency();

  const layout = useMemo(() => {
    const keywords = analysis?.keywords ?? [];
    return keywords.length > 0 ? layoutWordCloud(keywords) : null;
  }, [analysis]);
  const yearRange = coveredYearRange(analysis?.source_periods);

  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);
  const hoveredWord =
    layout && hoveredIndex !== null ? layout.placed[hoveredIndex] : null;
  // 字級放大很多之後，tooltip 也跟著放大，避免相對於文字雲顯得過小。
  const tooltipW = 340;
  const tooltipH = 92;
  const tooltip =
    layout && hoveredWord
      ? {
          x: clamp(
            hoveredWord.x - tooltipW / 2,
            layout.bounds.minX + 2,
            layout.bounds.minX + layout.bounds.width - tooltipW - 2,
          ),
          y: Math.max(
            layout.bounds.minY + 2,
            hoveredWord.y - hoveredWord.boxH / 2 - tooltipH - 14,
          ),
        }
      : null;

  return (
    <Card>
      <CardHeader>
        <p className="text-xs font-bold uppercase tracking-[0.16em] text-accent-slate">
          Topic Importance
        </p>
        <CardTitle className="text-lg font-bold text-slate-900">
          青年關注議題重要程度文字雲
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {isLoading ? (
          <Skeleton className="h-[320px] w-full rounded-xl" />
        ) : isError || !layout ? (
          <section
            role="alert"
            className="flex min-h-[220px] flex-col items-center justify-center gap-3 rounded-xl border border-red-200 bg-red-50 p-8 text-center"
          >
            <p className="text-sm text-red-600">
              {error instanceof Error ? error.message : "議題文字雲資料載入失敗，請稍後再試。"}
            </p>
            <Button variant="destructive" onClick={() => refetch()}>
              重新載入
            </Button>
          </section>
        ) : (
          <>
            <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
              <svg
                viewBox={`${layout.bounds.minX} ${layout.bounds.minY} ${layout.bounds.width} ${layout.bounds.height}`}
                className="block h-auto max-h-[380px] w-full"
                role="img"
                aria-label="青年關注議題重要程度文字雲，滑鼠移至字詞可查看出現次數"
              >
                {layout.placed.map((word, index) => (
                  <text
                    key={word.label}
                    x={word.x}
                    y={word.y}
                    textAnchor="middle"
                    dominantBaseline="central"
                    fontSize={word.fontSize}
                    fontWeight={fontWeightFor(word.weight)}
                    className={cn(word.fill, "cursor-default")}
                    transform={
                      word.rotate
                        ? `rotate(${word.rotate} ${word.x} ${word.y})`
                        : undefined
                    }
                    onMouseEnter={() => setHoveredIndex(index)}
                    onMouseLeave={() => setHoveredIndex(null)}
                  >
                    <title>
                      {word.label}：出現次數 {word.termFrequency.toLocaleString("zh-Hant-TW")}
                    </title>
                    {word.label}
                  </text>
                ))}

                {hoveredWord && tooltip && (
                  <g pointerEvents="none">
                    <rect
                      x={tooltip.x}
                      y={tooltip.y}
                      width={tooltipW}
                      height={tooltipH}
                      rx={14}
                      fill="#10233f"
                    />
                    <text
                      x={tooltip.x + tooltipW / 2}
                      y={tooltip.y + 36}
                      textAnchor="middle"
                      dominantBaseline="central"
                      fill="#ffffff"
                      fontSize={32}
                      fontWeight={700}
                    >
                      {hoveredWord.label}
                    </text>
                    <text
                      x={tooltip.x + tooltipW / 2}
                      y={tooltip.y + 68}
                      textAnchor="middle"
                      dominantBaseline="central"
                      fill="#cbd5e1"
                      fontSize={22}
                    >
                      出現次數 {hoveredWord.termFrequency.toLocaleString("zh-Hant-TW")}
                    </text>
                  </g>
                )}
              </svg>
            </div>
            <p className="text-[11px] text-slate-400">
              {yearRange
                ? `資料為民國 ${yearRange} 年所有可用提案與會議紀錄合併的議題關鍵字重要程度。`
                : "資料為所有可用提案與會議紀錄合併的議題關鍵字重要程度。"}
            </p>
          </>
        )}
      </CardContent>
    </Card>
  );
}
