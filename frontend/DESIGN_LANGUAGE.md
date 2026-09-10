# 設計語言（Design Language）

新北青年機會地圖 Dashboard 全站共用的視覺設計 token。所有頁面／板塊皆應
透過 Tailwind theme（`tailwind.config.ts`）取用這些顏色，不得在元件中
寫死色碼（SVG choropleth 依資料動態計算顏色除外）。

## 色彩 Token

| Token | 色碼 | 用途 |
| --- | --- | --- |
| `primary` | `#005599` | 主色：導覽列品牌色、主要按鈕、選取狀態、連結 |
| `background` | `#f8f9ff` | 頁面背景 |
| `surface` | `#ffffff` | 卡片／容器背景 |
| `accent.teal` | `#0f9d8a` | 正向趨勢、成功狀態輔助色 |
| `accent.warning` | `#f2994a` | 警示、待處理狀態輔助色 |
| `accent.slate` | `#5b7799` | 次要文字、標籤、圖例 |
| `risk.low` | `#1f9d6c` | 留才風險等級：低 |
| `risk.medium` | `#f2994a` | 留才風險等級：中 |
| `risk.high` | `#d64545` | 留才風險等級：高 |

## 字級

沿用 Tailwind 預設字級尺度（`text-xs` ~ `text-4xl`），標題一律使用
`font-bold` / `font-extrabold`，內文使用系統預設字重。

## 間距與圓角

- 卡片圓角：`rounded-2xl`（1rem）
- 卡片內距：`p-5`
- 版面最大寬度：`max-w-[1440px]`，左右內距 `px-6`

## Icon

全站使用 `lucide-react`，尺寸預設 20px，顏色跟隨文字色（`currentColor`）。
