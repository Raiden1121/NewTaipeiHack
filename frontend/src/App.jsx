import { useEffect, useState } from 'react'
import { feature } from 'topojson-client'
import TownMap from './components/TownMap'

const DATA_URL = '/taiwan-towns-65000.topo.json'

function getErrorMessage(error) {
  if (error instanceof Error && error.message) {
    return error.message
  }

  return '行政區資料載入失敗，請稍後再試。'
}

export default function App() {
  const [features, setFeatures] = useState([])
  const [selectedTownId, setSelectedTownId] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [reloadKey, setReloadKey] = useState(0)

  useEffect(() => {
    const controller = new AbortController()

    async function loadTopology() {
      setLoading(true)
      setError(null)

      try {
        const response = await fetch(DATA_URL, { signal: controller.signal })
        if (!response.ok) {
          throw new Error(`資料請求失敗（HTTP ${response.status}）`)
        }

        const topology = await response.json()
        const mapObject = topology?.objects?.map
        if (!mapObject) {
          throw new Error('TopoJSON 缺少 objects.map 資料。')
        }

        const collection = feature(topology, mapObject)
        const nextFeatures = collection.features ?? []
        setFeatures(nextFeatures)
        setSelectedTownId(nextFeatures[0]?.properties?.id ?? null)
      } catch (loadError) {
        if (loadError.name !== 'AbortError') {
          setFeatures([])
          setSelectedTownId(null)
          setError(getErrorMessage(loadError))
        }
      } finally {
        if (!controller.signal.aborted) {
          setLoading(false)
        }
      }
    }

    loadTopology()

    return () => controller.abort()
  }, [reloadKey])

  const showEmptyState = !loading && !error && features.length === 0

  return (
    <main className="app-shell">
      <header className="page-header">
        <div>
          <p className="eyebrow">NEW TAIPEI · DATA VIEW</p>
          <h1>新北市行政區地圖</h1>
          <p className="page-subtitle">
            以 TopoJSON 呈現新北市 29 個行政區的邊界資料。
          </p>
        </div>
        <div className="data-badge" aria-label={`目前載入 ${features.length} 個行政區`}>
          <span className="data-badge__dot" />
          <span>{features.length || '--'} 個行政區</span>
        </div>
      </header>

      {loading && (
        <section className="state-panel" aria-live="polite">
          <span className="loader" aria-hidden="true" />
          <div>
            <h2>正在載入地圖資料</h2>
            <p>正在解析 650000 行政區 TopoJSON。</p>
          </div>
        </section>
      )}

      {error && (
        <section className="state-panel state-panel--error" role="alert">
          <span className="state-icon" aria-hidden="true">!</span>
          <div>
            <h2>地圖資料載入失敗</h2>
            <p>{error}</p>
            <button
              className="button button--light"
              type="button"
              onClick={() => setReloadKey((value) => value + 1)}
            >
              重新載入
            </button>
          </div>
        </section>
      )}

      {showEmptyState && (
        <section className="state-panel" role="status">
          <span className="state-icon" aria-hidden="true">∅</span>
          <div>
            <h2>找不到行政區資料</h2>
            <p>目前的 TopoJSON 沒有可顯示的 Polygon。</p>
          </div>
        </section>
      )}

      {!loading && !error && features.length > 0 && (
        <section className="map-card map-card--solo" aria-labelledby="map-title">
          <div className="card-heading">
            <div>
              <p className="section-kicker">INTERACTIVE MAP</p>
              <h2 id="map-title">行政區分布</h2>
            </div>
            <span className="card-hint">Hover / Click</span>
          </div>
          <TownMap
            features={features}
            selectedTownId={selectedTownId}
            onSelectTown={setSelectedTownId}
          />
        </section>
      )}
    </main>
  )
}
