import { useMemo, useState } from 'react'
import { geoCentroid, geoMercator, geoPath } from 'd3-geo'

const MAP_WIDTH = 760
const MAP_HEIGHT = 560
const TOWN_COLORS = [
  '#bde0fe',
  '#a2d2ff',
  '#cdeac0',
  '#f9d5a7',
  '#f7c8e0',
  '#d9c2f0',
]

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max)
}

export default function TownMap({ features, selectedTownId, onSelectTown }) {
  const [hoveredTownId, setHoveredTownId] = useState(null)

  const collection = useMemo(
    () => ({ type: 'FeatureCollection', features }),
    [features],
  )

  const projection = useMemo(
    () => geoMercator().fitSize([MAP_WIDTH, MAP_HEIGHT], collection),
    [collection],
  )

  const pathGenerator = useMemo(() => geoPath(projection), [projection])
  const hoveredTown = features.find(
    (town) => town.properties?.id === hoveredTownId,
  )
  const tooltipPoint = hoveredTown ? pathGenerator.centroid(hoveredTown) : null
  const tooltipX = tooltipPoint
    ? clamp(tooltipPoint[0] - 54, 12, MAP_WIDTH - 132)
    : 0
  const tooltipY = tooltipPoint
    ? clamp(tooltipPoint[1] - 42, 12, MAP_HEIGHT - 48)
    : 0

  return (
    <div className="map-stage">
      <svg
        className="town-map"
        viewBox={`0 0 ${MAP_WIDTH} ${MAP_HEIGHT}`}
        role="img"
        aria-label="新北市行政區互動地圖"
      >
        <defs>
          <filter id="map-shadow" x="-20%" y="-20%" width="140%" height="140%">
            <feDropShadow dx="0" dy="8" stdDeviation="8" floodOpacity="0.12" />
          </filter>
        </defs>
        <g filter="url(#map-shadow)">
          {features.map((town, index) => {
            const id = town.properties?.id
            const name = town.properties?.name ?? '未命名行政區'
            const className = [
              'town-path',
              id === selectedTownId ? 'is-selected' : '',
              id === hoveredTownId ? 'is-hovered' : '',
            ]
              .filter(Boolean)
              .join(' ')

            return (
              <path
                className={className}
                d={pathGenerator(town)}
                key={id}
                aria-label={name}
                data-town-id={id}
                style={{ '--town-fill': TOWN_COLORS[index % TOWN_COLORS.length] }}
                onMouseEnter={() => setHoveredTownId(id)}
                onMouseLeave={() => setHoveredTownId(null)}
                onClick={() => onSelectTown(id)}
              >
                <title>{name}</title>
              </path>
            )
          })}
        </g>
        {hoveredTown && tooltipPoint && (
          <g
            className="map-tooltip"
            pointerEvents="none"
            transform={`translate(${tooltipX} ${tooltipY})`}
          >
            <rect width="132" height="36" rx="9" />
            <text x="66" y="23" textAnchor="middle">
              {hoveredTown.properties?.name ?? '未命名行政區'}
            </text>
          </g>
        )}
      </svg>
      <div className="map-legend">
        <span className="map-legend__swatch" />
        <span>行政區邊界</span>
        <span className="map-legend__selected" />
        <span>目前選取</span>
      </div>
    </div>
  )
}
