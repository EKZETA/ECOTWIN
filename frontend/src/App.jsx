import { useEffect, useMemo, useState } from 'react'
import DeckGL from '@deck.gl/react'
import { COORDINATE_SYSTEM, OrthographicView } from '@deck.gl/core'
import { IconLayer, PathLayer, PolygonLayer, ScatterplotLayer } from '@deck.gl/layers'
import './App.css'

const API_URL = import.meta.env.VITE_API_BASE_URL || ''
const WS_URL = import.meta.env.VITE_WS_URL || `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}/ws/telemetry`
const vehicleColors = ['#f07c5d', '#57a6c4', '#e9bd58', '#82b77d', '#a18bc4', '#e8e4d8']
const signalColors = {
  red: '#ff5148',
  yellow: '#ffc247',
  green: '#43d98b',
  unknown: '#536267',
}
const pollutionStops = [
  { at: 0, color: [65, 190, 132] },
  { at: 0.45, color: [246, 207, 82] },
  { at: 0.75, color: [244, 130, 67] },
  { at: 1, color: [232, 62, 57] },
]

function pollutionColor(value, maximum) {
  const intensity = maximum > 0 ? Math.min(1, value / maximum) : 0
  const upperIndex = pollutionStops.findIndex((stop) => stop.at >= intensity)
  const lower = pollutionStops[Math.max(0, upperIndex - 1)]
  const upper = pollutionStops[Math.max(0, upperIndex)]
  const blend = upper.at === lower.at ? 0 : (intensity - lower.at) / (upper.at - lower.at)
  const rgb = lower.color.map((channel, index) => Math.round(channel + (upper.color[index] - channel) * blend))
  return [...rgb, Math.round(35 + intensity * 125)]
}

const iconMapping = Object.fromEntries([
  ...vehicleColors.map((_, index) => [
    `vehicle-${index}`,
    { x: index * 32, y: 0, width: 32, height: 64, anchorX: 16, anchorY: 32, mask: false },
  ]),
  ...Object.keys(signalColors).map((status, index) => [
    `signal-${status}`,
    { x: (vehicleColors.length + index) * 32, y: 0, width: 32, height: 64, anchorX: 16, anchorY: 32, mask: false },
  ]),
])
const iconAtlas = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(`
  <svg xmlns="http://www.w3.org/2000/svg" width="${(vehicleColors.length + Object.keys(signalColors).length) * 32}" height="64" viewBox="0 0 ${(vehicleColors.length + Object.keys(signalColors).length) * 32} 64">
    ${vehicleColors.map((color, index) => `
      <g transform="translate(${index * 32},0)">
        <rect x="3" y="17" width="4" height="11" rx="2" fill="#263238"/>
        <rect x="25" y="17" width="4" height="11" rx="2" fill="#263238"/>
        <rect x="3" y="38" width="4" height="11" rx="2" fill="#263238"/>
        <rect x="25" y="38" width="4" height="11" rx="2" fill="#263238"/>
        <path d="M10 8h12l4 8v34l-4 7H10l-4-7V16z" fill="${color}" stroke="#263238" stroke-width="1.5"/>
        <path d="M10 15h12l2 8H8z" fill="#b8dce1" stroke="#263238" stroke-width="1"/>
        <path d="M8 39h16l-2 8H10z" fill="#76969d" stroke="#263238" stroke-width="1"/>
        <path d="M9 11h14" stroke="#ffffff" stroke-opacity=".65" stroke-width="1.5"/>
      </g>
    `).join('')}
    ${Object.entries(signalColors).map(([status, activeColor], index) => {
      const x = (vehicleColors.length + index) * 32
      const bulbs = ['red', 'yellow', 'green']
      return `
        <g transform="translate(${x},0)">
          <rect x="10" y="9" width="12" height="46" rx="5" fill="#202c30" stroke="#d5ddd5" stroke-width="1.5"/>
          ${bulbs.map((bulb, bulbIndex) => {
            const y = 19 + bulbIndex * 13
            const isLit = bulb === status
            const color = isLit ? activeColor : '#465257'
            return `
              ${isLit ? `<circle cx="16" cy="${y}" r="6" fill="${activeColor}" opacity=".24"/>` : ''}
              <circle cx="16" cy="${y}" r="3.5" fill="${color}" stroke="${isLit ? '#fff4d7' : '#303c40'}" stroke-width=".6"/>
            `
          }).join('')}
          <path d="M16 55v5" stroke="#455256" stroke-width="2"/>
        </g>
      `
    }).join('')}
  </svg>
`)}` 

const emptyTelemetry = {
  step: 0,
  time_s: 0,
  active_vehicles: 0,
  avg_speed_kmh: 0,
  avg_wait_s: 0,
  total_co2_kg: 0,
  vehicles: [],
  traffic_lights: [],
  pollution_grid: null,
  agent: null,
}
const emptyPollutionValues = []

function MetricChart({ label, unit, value, data, dataKey, color }) {
  const width = 320
  const height = 64
  const values = data.map((point) => point[dataKey])
  const minimum = Math.min(...values)
  const maximum = Math.max(...values)
  const padding = Math.max((maximum - minimum) * 0.12, maximum * 0.04, 0.05)
  const rangeMinimum = Math.max(0, minimum - padding)
  const rangeMaximum = maximum + padding
  const points = values.map((sample, index) => ({
    x: values.length > 1 ? (index / (values.length - 1)) * width : width,
    y: height - ((sample - rangeMinimum) / (rangeMaximum - rangeMinimum)) * height,
  }))
  const line = points.map((point, index) => `${index === 0 ? 'M' : 'L'} ${point.x} ${point.y}`).join(' ')
  const area = `${line} L ${width} ${height} L 0 ${height} Z`

  return (
    <section className="trend-chart" aria-label={`${label} trend`}>
      <div className="trend-heading">
        <span>{label}</span>
        <strong>{value}<small> {unit}</small></strong>
      </div>
      <svg className="trend-plot" viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`${label}: ${value} ${unit}`}>
        {[0.25, 0.5, 0.75].map((fraction) => (
          <line key={fraction} x1="0" x2={width} y1={height * fraction} y2={height * fraction} className="trend-gridline" />
        ))}
        <path d={area} fill={color} fillOpacity="0.12" />
        <path d={line} fill="none" stroke={color} strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
        {points.length > 0 && <circle cx={points.at(-1).x} cy={points.at(-1).y} r="3" fill={color} />}
      </svg>
      <span className="trend-caption">LIVE · LAST {data.length ? Math.round(data.at(-1).time_s - data[0].time_s) : 0} SIM S</span>
    </section>
  )
}

function App() {
  const [network, setNetwork] = useState(null)
  const [telemetry, setTelemetry] = useState(emptyTelemetry)
  const [metricHistory, setMetricHistory] = useState([])
  const [isPaused, setIsPaused] = useState(false)
  const [showHeatmap, setShowHeatmap] = useState(true)
  const [connection, setConnection] = useState('connecting')
  const [agentStatus, setAgentStatus] = useState({ status: 'connecting', decisions: 0 })
  const [error, setError] = useState('')

  useEffect(() => {
    let active = true

    fetch(`${API_URL}/api/network`)
      .then((response) => {
        if (!response.ok) throw new Error('Network request failed')
        return response.json()
      })
      .then((data) => {
        if (active) setNetwork(data)
      })
      .catch(() => {
        if (active) setError('Could not load the city grid. Is the backend running?')
      })

    fetch(`${API_URL}/api/agent/status`)
      .then((response) => {
        if (!response.ok) throw new Error('Agent status request failed')
        return response.json()
      })
      .then((status) => {
        if (active) setAgentStatus(status)
      })
      .catch(() => {
        if (active) setAgentStatus({ status: 'backend_unavailable', decisions: 0 })
      })

    const socket = new WebSocket(WS_URL)
    socket.onopen = () => {
      if (active) setConnection('live')
    }
    socket.onmessage = (event) => {
      if (active) {
        const frame = JSON.parse(event.data)
        setTelemetry(frame)
        if (frame.agent) setAgentStatus(frame.agent)
        setMetricHistory((history) => {
          const latest = history.at(-1)
          if (latest && frame.step < latest.step) return [frame]
          if (latest && frame.time_s - latest.time_s < 5) return history
          return [...history, frame].slice(-60)
        })
      }
    }
    socket.onerror = () => {
      if (active) {
        setConnection('offline')
        setError('Telemetry is offline. Start the FastAPI backend to connect.')
      }
    }
    socket.onclose = () => {
      if (active) setConnection('offline')
    }

    return () => {
      active = false
      socket.close()
    }
  }, [])

  const center = network
    ? [(network.bbox.min_x + network.bbox.max_x) / 2, (network.bbox.min_y + network.bbox.max_y) / 2, 0]
    : [0, 0, 0]
  const pollutionGrid = telemetry.pollution_grid
  const pollutionValues = pollutionGrid?.values || emptyPollutionValues
  const maxPollution = Math.max(0, ...pollutionValues.flat())

  const baseLayers = useMemo(() => {
    if (!network) return []

    return [
      new ScatterplotLayer({
        id: 'junction-surfaces',
        data: network.junctions,
        coordinateSystem: COORDINATE_SYSTEM.CARTESIAN,
        getPosition: (junction) => [junction.x, junction.y],
        getRadius: (junction) => junction.has_tls ? 12 : 8,
        radiusUnits: 'meters',
        getFillColor: [53, 64, 65, 255],
        stroked: true,
        getLineColor: [112, 120, 113, 255],
        lineWidthMinPixels: 1,
      }),
      new PathLayer({
        id: 'road-shoulders',
        data: network.edges,
        coordinateSystem: COORDINATE_SYSTEM.CARTESIAN,
        getPath: (edge) => edge.coordinates,
        getColor: [111, 119, 110, 255],
        getWidth: (edge) => edge.lanes * 3.2 + 1.5,
        widthUnits: 'meters',
        capRounded: true,
        jointRounded: true,
      }),
      new PathLayer({
        id: 'road-asphalt',
        data: network.edges,
        coordinateSystem: COORDINATE_SYSTEM.CARTESIAN,
        getPath: (edge) => edge.coordinates,
        getColor: [54, 65, 67, 255],
        getWidth: (edge) => edge.lanes * 3.2,
        widthUnits: 'meters',
        capRounded: true,
        jointRounded: true,
      }),
      new PathLayer({
        id: 'lane-markings',
        data: network.edges,
        coordinateSystem: COORDINATE_SYSTEM.CARTESIAN,
        getPath: (edge) => edge.coordinates,
        getColor: [220, 213, 177, 145],
        getWidth: 1,
        widthUnits: 'pixels',
        capRounded: true,
        jointRounded: true,
      }),
      new ScatterplotLayer({
        id: 'junctions',
        data: network.junctions,
        coordinateSystem: COORDINATE_SYSTEM.CARTESIAN,
        getPosition: (junction) => [junction.x, junction.y],
        getRadius: 2.5,
        radiusUnits: 'meters',
        getFillColor: [150, 159, 146, 255],
        pickable: true,
      }),
    ]
  }, [network])

  const liveLayers = useMemo(() => {
    if (!network) return []

    const trafficLights = new Map(telemetry.traffic_lights.map((light) => [light.id, light]))
    const signalJunctions = network.junctions
      .filter((junction) => junction.has_tls)
      .map((junction) => {
        const light = trafficLights.get(junction.id)
        const state = light?.state || ''
        const signalStatus = /[yY]/.test(state)
          ? 'yellow'
          : /[gG]/.test(state)
            ? 'green'
            : /[rR]/.test(state)
              ? 'red'
              : 'unknown'
        return { ...junction, signalStatus, phase: light?.phase }
      })

    const pollutionCells = showHeatmap && pollutionGrid
      ? pollutionValues.flatMap((row, rowIndex) => row
        .map((value, columnIndex) => ({
          id: `CO₂ cell ${rowIndex + 1}-${columnIndex + 1}`,
          value,
          bounds: [
            pollutionGrid.min_x + columnIndex * (pollutionGrid.max_x - pollutionGrid.min_x) / row.length,
            pollutionGrid.min_y + rowIndex * (pollutionGrid.max_y - pollutionGrid.min_y) / pollutionValues.length,
            pollutionGrid.min_x + (columnIndex + 1) * (pollutionGrid.max_x - pollutionGrid.min_x) / row.length,
            pollutionGrid.min_y + (rowIndex + 1) * (pollutionGrid.max_y - pollutionGrid.min_y) / pollutionValues.length,
          ],
        }))
        .filter((cell) => cell.value > 0))
      : []

    return [
      ...(pollutionCells.length > 0 ? [new PolygonLayer({
        id: 'carbon-heatmap',
        data: pollutionCells,
        coordinateSystem: COORDINATE_SYSTEM.CARTESIAN,
        getPolygon: (cell) => [
          [cell.bounds[0], cell.bounds[1]],
          [cell.bounds[2], cell.bounds[1]],
          [cell.bounds[2], cell.bounds[3]],
          [cell.bounds[0], cell.bounds[3]],
        ],
        getFillColor: (cell) => pollutionColor(cell.value, maxPollution),
        stroked: false,
        pickable: true,
      })] : []),
      new IconLayer({
        id: 'vehicles',
        data: telemetry.vehicles,
        coordinateSystem: COORDINATE_SYSTEM.CARTESIAN,
        getPosition: (vehicle) => [vehicle.x, vehicle.y],
        iconAtlas,
        iconMapping,
        getIcon: (vehicle) => {
          const hash = [...vehicle.id].reduce((sum, character) => sum + character.charCodeAt(0), 0)
          return `vehicle-${hash % vehicleColors.length}`
        },
        getAngle: (vehicle) => vehicle.angle,
        getSize: 24,
        sizeUnits: 'pixels',
        pickable: true,
      }),
      new IconLayer({
        id: 'traffic-lights',
        data: signalJunctions,
        coordinateSystem: COORDINATE_SYSTEM.CARTESIAN,
        getPosition: (junction) => [junction.x, junction.y],
        iconAtlas,
        iconMapping,
        getIcon: (junction) => `signal-${junction.signalStatus}`,
        getSize: 22,
        sizeUnits: 'pixels',
        pickable: true,
      }),
    ]
  }, [network, telemetry, showHeatmap, pollutionGrid, pollutionValues, maxPollution])

  const layers = [...baseLayers, ...liveLayers]

  async function simulationAction(action) {
    try {
      const response = await fetch(`${API_URL}/api/simulation/${action}`, { method: 'POST' })
      if (!response.ok) throw new Error('Simulation request failed')
      if (action === 'pause') setIsPaused((paused) => !paused)
      if (action === 'start') setIsPaused(false)
      if (action === 'reset') {
        setIsPaused(false)
        setTelemetry(emptyTelemetry)
        setMetricHistory([])
        setError('')
      }
    } catch {
      setError('Simulation control failed. Check that the backend and SUMO are available.')
    }
  }

  return (
    <main className="app-shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">SUMO / DECK.GL</p>
          <h1>City Grid Monitor</h1>
        </div>
        <div className={`connection connection-${connection}`}>
          <span className="connection-dot" /> {connection === 'live' ? 'Live telemetry' : connection}
        </div>
      </header>

      <section className="toolbar" aria-label="Simulation controls">
        <div className="toolbar-copy">
          <strong>Simulation</strong>
          <span>Step {telemetry.step} / {telemetry.time_s}s</span>
        </div>
        <div className="actions">
          <button type="button" onClick={() => simulationAction(isPaused ? 'start' : 'pause')}>
            {isPaused ? 'Resume' : 'Pause'}
          </button>
          <button type="button" className="primary" onClick={() => simulationAction('reset')}>Reset run</button>
        </div>
      </section>

      {error && <p className="error-banner">{error}</p>}

      <section className="workspace">
        <div className="map-frame">
          {network ? (
            <DeckGL
              views={new OrthographicView({ id: 'city-grid' })}
              initialViewState={{ target: center, zoom: -1 }}
              controller
              layers={layers}
              getTooltip={({ object }) => {
                if (!object?.id) return null
                if (object.value !== undefined) {
                  return { text: `${object.id} · ${object.value.toFixed(1)} mg CO₂/cell` }
                }
                if (object.signalStatus) {
                  return { text: `${object.id} · ${object.signalStatus.toUpperCase()}${object.phase !== undefined ? ` · phase ${object.phase}` : ''}` }
                }
                if (object.speed_kmh !== undefined) {
                  return { text: `${object.id} · ${object.speed_kmh} km/h` }
                }
                return { text: object.id }
              }}
            />
          ) : <div className="map-loading">Loading city grid...</div>}

          <button
            type="button"
            className={`map-overlay-control${showHeatmap ? ' is-active' : ''}`}
            aria-pressed={showHeatmap}
            onClick={() => setShowHeatmap((visible) => !visible)}
          >
            <span className="heatmap-control-mark" aria-hidden="true" />
            CO₂ heatmap {showHeatmap ? 'on' : 'off'}
          </button>
          <div className="map-label">LIVE STREET VIEW <span>·</span> SUMO CITY GRID</div>
          <div className="legend">
            <span className="legend-road" /> roads
            <span className="legend-car" /> vehicles
            <span className="legend-heatmap" /> CO₂ <strong>{maxPollution.toFixed(1)} mg/cell</strong>
            <span className="legend-signal legend-signal-green" /> green
            <span className="legend-signal legend-signal-yellow" /> yellow
            <span className="legend-signal legend-signal-red" /> red
          </div>
        </div>

        <aside className="stats-panel">
          <p className="eyebrow">Live readout</p>
          <section className={`agent-status agent-status-${agentStatus.status}`} aria-live="polite">
            <span className="agent-status-indicator" />
            <div>
              <strong>
                {agentStatus.status === 'active'
                  ? 'RL policy active'
                  : agentStatus.status === 'missing_checkpoint'
                    ? 'RL checkpoint missing'
                    : agentStatus.status === 'load_failed' || agentStatus.status === 'runtime_error'
                      ? 'RL policy error'
                      : agentStatus.status === 'backend_unavailable'
                        ? 'Backend unavailable'
                        : 'Checking RL policy'}
              </strong>
              <span>
                {agentStatus.status === 'active'
                  ? `${agentStatus.decisions} decisions made`
                  : agentStatus.error || 'Waiting for backend status'}
              </span>
            </div>
          </section>
          <div className="stat-grid">
            <div><span>Vehicles</span><strong>{telemetry.active_vehicles}</strong></div>
            <div><span>Avg speed</span><strong>{telemetry.avg_speed_kmh}<small> km/h</small></strong></div>
            <div><span>Avg wait</span><strong>{telemetry.avg_wait_s}<small> sec</small></strong></div>
            <div><span>Total CO2</span><strong>{telemetry.total_co2_kg}<small> kg</small></strong></div>
          </div>
          <div className="metric-trends">
            <MetricChart
              label="Total CO₂ emitted"
              unit="kg"
              value={telemetry.total_co2_kg}
              data={metricHistory.length ? metricHistory : [telemetry]}
              dataKey="total_co2_kg"
              color="#c45e44"
            />
            <MetricChart
              label="Average wait time"
              unit="sec"
              value={telemetry.avg_wait_s}
              data={metricHistory.length ? metricHistory : [telemetry]}
              dataKey="avg_wait_s"
              color="#167c73"
            />
          </div>
          <div className="how-it-works">
            <p className="eyebrow">How this connects</p>
            <p>The map comes from <code>/api/network</code>. Moving vehicles arrive through the <code>/ws/telemetry</code> WebSocket.</p>
          </div>
        </aside>
      </section>
    </main>
  )
}

export default App
