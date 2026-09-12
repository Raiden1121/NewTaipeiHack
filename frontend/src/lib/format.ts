const UNAVAILABLE_LABEL = "資料待補";

export function formatOrFallback<T>(
  value: T | null | undefined,
  format: (value: T) => string,
  fallback: string = UNAVAILABLE_LABEL,
): string {
  return value === null || value === undefined ? fallback : format(value);
}

export function formatInt(value: number): string {
  return new Intl.NumberFormat("zh-Hant-TW").format(Math.round(value));
}

export function formatPercent(value: number, decimals = 1): string {
  return `${value.toFixed(decimals)}%`;
}

export function formatSignedPercent(value: number, decimals = 1): string {
  return `${value > 0 ? "+" : ""}${value.toFixed(decimals)}%`;
}

/** TWD_thousand（千元）→ 億元字串，例：196153 → "1.96 億"。1 億 = 100,000 千元。 */
export function formatThousandAsYi(valueThousand: number, decimals = 2): string {
  return `${(valueThousand / 100_000).toFixed(decimals)} 億`;
}

/** 元/坪 → 萬元/坪，例：574657.83 → "57.47"。 */
export function formatYuanAsWan(valueYuan: number, decimals = 2): string {
  return (valueYuan / 10_000).toFixed(decimals);
}
