import { useMemo } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { useYouthTopicWeight } from "@/lib/api/queries";
import type { YouthTopicWeightTopic } from "@/lib/api/types";

const FONT_SIZE: Record<number, number> = {
  5: 32,
  4: 25,
  3: 20,
  2: 16,
  1: 13,
};

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
}

interface Box {
  x: number;
  y: number;
  w: number;
  h: number;
}

// 依重要程度由大到小，沿螺旋外擴尋找不與既有詞碰撞的位置（AABB 碰撞偵測）。
function layoutWordCloud(topics: YouthTopicWeightTopic[]): {
  placed: PlacedWord[];
  viewBox: string;
} {
  const sorted = [...topics].sort((a, b) => b.weight - a.weight);
  const boxes: Box[] = [];
  const placed: PlacedWord[] = [];

  sorted.forEach((topic, index) => {
    const fontSize = FONT_SIZE[topic.weight] ?? FONT_SIZE[1];
    const vertical = seededUnit(index * 3 + 1) > 0.88;
    const textW = topic.label.length * fontSize + 14;
    const textH = fontSize + 12;
    const w = vertical ? textH : textW;
    const h = vertical ? textW : textH;

    let angle = seededUnit(index + 1) * Math.PI * 2;
    let radius = 0;
    let x = 0;
    let y = 0;

    for (let iter = 0; iter < 8000; iter += 1) {
      x = Math.cos(angle) * radius;
      y = Math.sin(angle) * radius * 0.6;
      const hit = boxes.some(
        (b) =>
          Math.abs(b.x - x) * 2 < b.w + w && Math.abs(b.y - y) * 2 < b.h + h,
      );
      if (!hit) break;
      angle += 0.22;
      radius += 0.5;
    }

    boxes.push({ x, y, w, h });
    placed.push({
      label: topic.label,
      x,
      y,
      fontSize,
      weight: topic.weight,
      rotate: vertical ? -90 : 0,
      fill: FILL_PALETTE[index % FILL_PALETTE.length],
    });
  });

  const pad = 10;
  const minX = Math.min(...boxes.map((b) => b.x - b.w / 2)) - pad;
  const maxX = Math.max(...boxes.map((b) => b.x + b.w / 2)) + pad;
  const minY = Math.min(...boxes.map((b) => b.y - b.h / 2)) - pad;
  const maxY = Math.max(...boxes.map((b) => b.y + b.h / 2)) + pad;

  return {
    placed,
    viewBox: `${minX} ${minY} ${maxX - minX} ${maxY - minY}`,
  };
}

export default function YouthTopicWordCloud() {
  const { data: analysis, isLoading, isError, error, refetch } = useYouthTopicWeight();

  const layout = useMemo(
    () => (analysis && analysis.topics.length > 0 ? layoutWordCloud(analysis.topics) : null),
    [analysis],
  );

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
                viewBox={layout.viewBox}
                className="block h-auto max-h-[380px] w-full"
                role="img"
                aria-label="青年關注議題重要程度文字雲"
              >
                {layout.placed.map((word) => (
                  <text
                    key={word.label}
                    x={word.x}
                    y={word.y}
                    textAnchor="middle"
                    dominantBaseline="central"
                    fontSize={word.fontSize}
                    fontWeight={
                      word.weight >= 4 ? 800 : word.weight >= 3 ? 700 : 600
                    }
                    className={word.fill}
                    transform={
                      word.rotate
                        ? `rotate(${word.rotate} ${word.x} ${word.y})`
                        : undefined
                    }
                  >
                    {word.label}
                  </text>
                ))}
              </svg>
            </div>
            <p className="text-[11px] text-slate-400">
              資料為民國 {analysis?.year_roc} 年議題重要程度分數。
            </p>
          </>
        )}
      </CardContent>
    </Card>
  );
}
