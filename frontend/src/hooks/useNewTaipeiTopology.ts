import { useEffect, useState } from "react";
import { feature } from "topojson-client";

const TOPOLOGY_URL = "/Map_NewTaipei.json";

export interface DistrictProperties {
  id: string;
  name: string;
}

export interface DistrictFeature {
  type: "Feature";
  properties: DistrictProperties;
  geometry: { type: string; coordinates: unknown };
}

export type TopologyStatus = "loading" | "ready" | "error";

export interface NewTaipeiTopology {
  features: DistrictFeature[];
  status: TopologyStatus;
  error: string | null;
}

/**
 * 載入 `public/Map_NewTaipei.json` TopoJSON 並轉為 GeoJSON features。
 * 地圖幾何載入為 CLAUDE.md 明列的「useEffect + fetch」既有例外。
 */
export function useNewTaipeiTopology(): NewTaipeiTopology {
  const [features, setFeatures] = useState<DistrictFeature[]>([]);
  const [status, setStatus] = useState<TopologyStatus>("loading");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();

    async function loadTopology() {
      setStatus("loading");
      try {
        const response = await fetch(TOPOLOGY_URL, {
          signal: controller.signal,
        });
        if (!response.ok) {
          throw new Error(`地圖幾何資料請求失敗（HTTP ${response.status}）`);
        }
        const topology = await response.json();
        const mapObject = topology?.objects?.map;
        if (!mapObject) {
          throw new Error("TopoJSON 缺少 objects.map 資料。");
        }
        const collection = feature(topology, mapObject) as unknown as {
          features: DistrictFeature[];
        };
        setFeatures(collection.features ?? []);
        setStatus("ready");
      } catch (loadError) {
        if ((loadError as Error).name !== "AbortError") {
          setFeatures([]);
          setError(
            loadError instanceof Error
              ? loadError.message
              : "地圖幾何資料載入失敗，請稍後再試。",
          );
          setStatus("error");
        }
      }
    }

    loadTopology();
    return () => controller.abort();
  }, []);

  return { features, status, error };
}
