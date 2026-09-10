import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

// 民國年，從 114 年往前推五年。
const YEARS = [114, 113, 112, 111, 110] as const;

interface TopicWord {
  label: string;
  weight: number; // 1（低）— 5（高），對應重要程度
}

// 佔位資料，待 Backend API 提供整理後結果。
const TOPIC_WORDS: TopicWord[] = [
  { label: "居住正義", weight: 5 },
  { label: "社會住宅", weight: 5 },
  { label: "就業支持", weight: 4 },
  { label: "青年創業", weight: 4 },
  { label: "公共參與", weight: 4 },
  { label: "交通通勤", weight: 3 },
  { label: "教育培力", weight: 3 },
  { label: "世代正義", weight: 3 },
  { label: "低薪困境", weight: 3 },
  { label: "租金補貼", weight: 3 },
  { label: "心理健康", weight: 2 },
  { label: "性別平等", weight: 2 },
  { label: "環境永續", weight: 2 },
  { label: "托育支持", weight: 2 },
  { label: "在地就業", weight: 2 },
  { label: "數位權利", weight: 1 },
  { label: "地方創生", weight: 1 },
  { label: "文化參與", weight: 1 },
  { label: "食品安全", weight: 1 },
  { label: "勞動權益", weight: 1 },
  { label: "青年審議", weight: 1 },
  { label: "社會安全網", weight: 1 },
];

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
function layoutWordCloud(words: TopicWord[]): {
  placed: PlacedWord[];
  viewBox: string;
} {
  const sorted = [...words].sort((a, b) => b.weight - a.weight);
  const boxes: Box[] = [];
  const placed: PlacedWord[] = [];

  sorted.forEach((word, index) => {
    const fontSize = FONT_SIZE[word.weight];
    const vertical = seededUnit(index * 3 + 1) > 0.88;
    const textW = word.label.length * fontSize + 14;
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
      label: word.label,
      x,
      y,
      fontSize,
      weight: word.weight,
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

const { placed: PLACED_WORDS, viewBox: CLOUD_VIEWBOX } =
  layoutWordCloud(TOPIC_WORDS);

export default function YouthTopicWordCloud() {
  // 佔位互動：切換年份尚未影響資料，待 Backend API 串接。
  const [year, setYear] = useState<(typeof YEARS)[number]>(YEARS[0]);

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
      <Card className="lg:col-span-1">
        <CardHeader>
          <p className="text-xs font-bold uppercase tracking-[0.16em] text-accent-slate">
            Year
          </p>
          <CardTitle className="text-lg font-bold text-slate-900">
            年份選擇
          </CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-2">
          {YEARS.map((option) => (
            <button
              key={option}
              type="button"
              onClick={() => setYear(option)}
              className={cn(
                "rounded-lg border px-4 py-2.5 text-left text-sm font-semibold transition-colors",
                option === year
                  ? "border-primary bg-primary/10 text-primary"
                  : "border-slate-200 text-slate-500 hover:bg-slate-50",
              )}
            >
              {option} 年
            </button>
          ))}
          <p className="mt-1 text-[11px] text-slate-400">
            切換年份為佔位互動，待 Backend API 串接。
          </p>
        </CardContent>
      </Card>

      <Card className="lg:col-span-2">
        <CardHeader>
          <p className="text-xs font-bold uppercase tracking-[0.16em] text-accent-slate">
            Topic Importance
          </p>
          <CardTitle className="text-lg font-bold text-slate-900">
            {year} 年青年關注議題重要程度文字雲
          </CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
            <svg
              viewBox={CLOUD_VIEWBOX}
              className="block h-auto max-h-[380px] w-full"
              role="img"
              aria-label={`${year} 年青年關注議題重要程度文字雲佔位`}
            >
              {PLACED_WORDS.map((word) => (
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
            議題與重要程度為佔位資料，待 Backend API 提供整理後結果。
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
