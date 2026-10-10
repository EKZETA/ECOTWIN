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
const signalAspects = ['red', 'yellow', 'green']
const signalCombinations = Array.from({ length: 1 << signalAspects.length }, (_, mask) => (
  signalAspects.filter((_, index) => mask & (1 << index)).join('-') || 'unknown'
))
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

function signalAspectCounts(state, linkIndices) {
  const counts = { red: 0, yellow: 0, green: 0 }
  for (const index of linkIndices) {
    const aspect = state[index]?.toLowerCase()
    if (aspect === 'r') counts.red += 1
    if (aspect === 'y') counts.yellow += 1
    if (aspect === 'g') counts.green += 1
  }
  return counts
}

function signalCombination(counts) {
  return signalAspects.filter((aspect) => counts[aspect] > 0).join('-') || 'unknown'
}

function trafficLightSignalCounts(state) {
  return {
    red: (state.match(/[rR]/g) || []).length,
    yellow: (state.match(/[yY]/g) || []).length,
    green: (state.match(/[gG]/g) || []).length,
  }
}

function agentStatusLabel(status) {
  return ({
    active: 'Active',
    backend_unavailable: 'Server unavailable',
    missing_checkpoint: 'Model not found',
    load_failed: 'Model failed to load',
    runtime_error: 'Runtime error',
    not_loaded: 'Not loaded',
    connecting: 'Connecting',
  })[status] || 'Unknown status'
}

function agentStatusDescription(status, error) {
  if (status === 'active') return 'The system adjusts traffic signal patterns based on traffic conditions and estimated CO₂.'
  if (error) return error
  if (status === 'backend_unavailable') return 'Start the simulation server to connect the dashboard.'
  if (status === 'missing_checkpoint') return 'The agent model file could not be found.'
  if (status === 'load_failed' || status === 'runtime_error') return 'Check the simulation server and agent model.'
  return 'Waiting for status from the simulation server.'
}

function signalStatusLabel(status) {
  return ({
    red: 'Red',
    yellow: 'Yellow',
    green: 'Green',
    unknown: 'Unknown',
  })[status] || 'Unknown'
}

const iconMapping = Object.fromEntries([
  ...vehicleColors.map((_, index) => [
    `vehicle-${index}`,
    { x: index * 32, y: 0, width: 32, height: 64, anchorX: 16, anchorY: 32, mask: false },
  ]),
  ...signalCombinations.map((combination, index) => [
    `signal-${combination}`,
    { x: (vehicleColors.length + index) * 32, y: 0, width: 32, height: 64, anchorX: 16, anchorY: 32, mask: false },
  ]),
])
const iconAtlas = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(`
  <svg xmlns="http://www.w3.org/2000/svg" width="${(vehicleColors.length + signalCombinations.length) * 32}" height="64" viewBox="0 0 ${(vehicleColors.length + signalCombinations.length) * 32} 64">
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
    ${signalCombinations.map((combination, index) => {
      const x = (vehicleColors.length + index) * 32
      const activeAspects = combination === 'unknown' ? [] : combination.split('-')
      return `
        <g transform="translate(${x},0)">
          <rect x="10" y="9" width="12" height="46" rx="5" fill="#202c30" stroke="#d5ddd5" stroke-width="1.5"/>
          ${signalAspects.map((aspect, bulbIndex) => {
            const y = 19 + bulbIndex * 13
            const activeColor = signalColors[aspect]
            const isLit = activeAspects.includes(aspect)
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
const numberFormat = new Intl.NumberFormat('id-ID', { maximumFractionDigits: 1 })

function formatNumber(value, digits = 1) {
  return new Intl.NumberFormat('id-ID', { maximumFractionDigits: digits }).format(value || 0)
}

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
    <section className="trend-chart" aria-label={`${label} chart`}>
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
      <span className="trend-caption">CHANGE · {data.length ? Math.round(data.at(-1).time_s - data[0].time_s) : 0} SIMULATION SECONDS</span>
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
        if (!response.ok) throw new Error('Road network request failed')
        return response.json()
      })
      .then((data) => {
        if (active) setNetwork(data)
      })
      .catch(() => {
        if (active) setError('Could not load the road network. Make sure the simulation server is running.')
      })

    fetch(`${API_URL}/api/agent/status`)
      .then((response) => {
        if (!response.ok) throw new Error('Controller status request failed')
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
        setError('Live data is disconnected. Start the simulation server to reconnect the dashboard.')
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
  const signalSummary = telemetry.traffic_lights.reduce((summary, light) => {
    const state = typeof light.state === 'string' ? light.state : ''
    const indications = trafficLightSignalCounts(state)
    summary.red += indications.red
    summary.yellow += indications.yellow
    summary.green += indications.green
    return summary
  }, { red: 0, yellow: 0, green: 0 })
  const hottestCells = pollutionValues.flatMap((row, rowIndex) => row
    .map((value, columnIndex) => ({
      id: `${rowIndex}-${columnIndex}`,
      value,
      column: columnIndex + 1,
      row: rowIndex + 1,
    })))
    .sort((first, second) => second.value - first.value)
    .slice(0, 3)

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
    const signalApproaches = network.junctions.flatMap((junction) => {
      const light = trafficLights.get(junction.id)
      if (!junction.has_tls || !light || typeof light.state !== 'string') return []
      return (junction.approaches || []).map((approach) => {
        const counts = signalAspectCounts(light.state, approach.link_indices)
        return {
          ...approach,
          id: `${junction.id} · ${approach.direction} approach`,
          junctionId: junction.id,
          phase: light.phase,
          counts,
          combination: signalCombination(counts),
        }
      })
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
        id: 'traffic-light-approaches',
        data: signalApproaches,
        coordinateSystem: COORDINATE_SYSTEM.CARTESIAN,
        getPosition: (approach) => [approach.x, approach.y],
        iconAtlas,
        iconMapping,
        getIcon: (approach) => `signal-${approach.combination}`,
        getSize: 18,
        sizeUnits: 'pixels',
        pickable: true,
      }),
    ]
  }, [network, telemetry, showHeatmap, pollutionGrid, pollutionValues, maxPollution])

  const layers = [...baseLayers, ...liveLayers]

  async function simulationAction(action) {
    try {
      const response = await fetch(`${API_URL}/api/simulation/${action}`, { method: 'POST' })
      if (!response.ok) throw new Error('Simulation control request failed')
      if (action === 'pause') setIsPaused((paused) => !paused)
      if (action === 'start') setIsPaused(false)
      if (action === 'reset') {
        setIsPaused(false)
        setTelemetry(emptyTelemetry)
        setMetricHistory([])
        setError('')
      }
    } catch {
      setError('Could not control the simulation. Make sure the server and SUMO are available.')
    }
  }

  return (
    <main className="app-shell">
      <header className="topbar">
        <div className="brand-lockup">
          <div className="brand-mark" aria-hidden="true">E</div>
          <div>
            <p className="eyebrow">ECOTWIN <span>/</span> CITY SIMULATION</p>
            <h1>City traffic &amp; emissions</h1>
            <p className="page-subtitle">Monitor vehicles, traffic signals, and estimated CO₂ in real time</p>
          </div>
        </div>
        <div className="header-tools">
          <div className={`connection connection-${connection}`} aria-live="polite">
            <span className="connection-dot" />
            <span>{connection === 'live' ? 'Connected' : connection === 'offline' ? 'Disconnected' : 'Connecting'}</span>
          </div>
          <div className="simulation-metrics">
            <div className="simulation-clock">
              <span>Simulation time</span>
              <strong>{formatNumber(telemetry.time_s, 1)}<small> s</small></strong>
            </div>
            <div className="simulation-clock simulation-steps">
              <span>Simulation steps</span>
              <strong>{numberFormat.format(telemetry.step)}</strong>
            </div>
          </div>
          <div className="header-actions">
            <button type="button" onClick={() => simulationAction(isPaused ? 'start' : 'pause')}>
              {isPaused ? 'Resume' : 'Pause'}
            </button>
            <button type="button" className="primary" onClick={() => simulationAction('reset')}>Restart simulation</button>
          </div>
        </div>
      </header>

      {error && <p className="error-banner" role="alert">{error}</p>}

      <section className="kpi-grid" aria-label="Live simulation metrics">
        <article className="kpi-card">
          <div className="kpi-topline"><span className="kpi-icon vehicle-icon" aria-hidden="true">V</span><span className="kpi-context">CURRENT</span></div>
          <span className="kpi-label">Vehicles on the road</span>
          <strong className="kpi-value">{formatNumber(telemetry.active_vehicles, 0)}</strong>
          <span className="kpi-footnote">Session peak: {formatNumber(telemetry.peak_vehicles, 0)}</span>
        </article>
        <article className="kpi-card">
          <div className="kpi-topline"><span className="kpi-icon speed-icon" aria-hidden="true">S</span><span className="kpi-context">AVERAGE</span></div>
          <span className="kpi-label">Vehicle speed</span>
          <strong className="kpi-value">{formatNumber(telemetry.avg_speed_kmh)}<small> km/h</small></strong>
          <span className="kpi-footnote">Across all moving vehicles</span>
        </article>
        <article className="kpi-card">
          <div className="kpi-topline"><span className="kpi-icon wait-icon" aria-hidden="true">W</span><span className="kpi-context">AVERAGE</span></div>
          <span className="kpi-label">Vehicle wait time</span>
          <strong className="kpi-value">{formatNumber(telemetry.avg_wait_s)}<small> sec</small></strong>
          <span className="kpi-footnote">Time vehicles spend stopped or waiting</span>
        </article>
        <article className="kpi-card kpi-carbon">
          <div className="kpi-topline"><span className="kpi-icon carbon-icon" aria-hidden="true">CO₂</span><span className="kpi-context">SESSION TOTAL</span></div>
          <span className="kpi-label">Estimated CO₂ emissions</span>
          <strong className="kpi-value">{formatNumber(telemetry.total_co2_kg, 2)}<small> kg</small></strong>
          <span className="kpi-footnote">{formatNumber(telemetry.step_co2_g, 2)} g in the last step</span>
        </article>
      </section>

      <section className="workspace">
        <div className="map-column">
          <div className="section-heading">
            <div>
              <p className="eyebrow">CITY MAP</p>
              <h2>Traffic conditions</h2>
            </div>
            <div className="map-heading-meta">
              <span><i className="heading-pulse" /> {network?.traffic_light_ids?.length || 0} intersections</span>
              <span>Step {numberFormat.format(telemetry.step)}</span>
            </div>
          </div>
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
                    return { text: `${object.id} · estimated ${formatNumber(object.value)} mg CO₂ per cell` }
                  }
                  if (object.link_indices) {
                    const { red, yellow, green } = object.counts
                    return {
                      text: `${object.id} · ${red} movements red · ${yellow} yellow · ${green} green · pattern ${object.phase + 1}`,
                    }
                  }
                  if (object.signalStatus) {
                    return { text: `${object.id} · ${signalStatusLabel(object.signalStatus)}${object.phase !== undefined ? ` · pattern ${object.phase + 1}` : ''}` }
                  }
                  if (object.speed_kmh !== undefined) {
                    return { text: `${object.id} · ${formatNumber(object.speed_kmh)} km/h` }
                  }
                  return { text: object.id }
                }}
              />
            ) : <div className="map-loading">Loading road network...</div>}

            <div className="map-status-bar">
              <span><i className="map-live-pulse" /> Simulation running</span>
              <span>{formatNumber(telemetry.active_vehicles, 0)} vehicles</span>
            </div>
            <button
              type="button"
              className={`map-overlay-control${showHeatmap ? ' is-active' : ''}`}
              aria-pressed={showHeatmap}
              onClick={() => setShowHeatmap((visible) => !visible)}
            >
              <span className="heatmap-control-mark" aria-hidden="true" />
              Show CO₂ map <strong>{showHeatmap ? 'On' : 'Off'}</strong>
            </button>
            <div className="map-label">SIMULATED ROAD NETWORK</div>
            <div className="legend">
              <span className="legend-road" /> Roads
              <span className="legend-car" /> Vehicles
              <span className="legend-heatmap" /> CO₂ low → high
              <span className="legend-divider" />
              <span><i className="legend-signal legend-signal-green" /> Green</span>
              <span><i className="legend-signal legend-signal-yellow" /> Yellow</span>
              <span><i className="legend-signal legend-signal-red" /> Red</span>
            </div>
          </div>

          <div className="map-summary">
            <div className="summary-title"><span>Signal directions</span><small>Movements, not physical lights</small></div>
            <div className="signal-summary">
              <span className="signal-count signal-count-green"><i />{formatNumber(signalSummary.green, 0)} green</span>
              <span className="signal-count signal-count-yellow"><i />{formatNumber(signalSummary.yellow, 0)} yellow</span>
              <span className="signal-count signal-count-red"><i />{formatNumber(signalSummary.red, 0)} red</span>
            </div>
            <div className="summary-separator" />
            <div className="summary-pollution">
              <span>Highest estimated CO₂ per cell</span>
              <strong>{formatNumber(maxPollution)} <small>mg/cell</small></strong>
            </div>
          </div>

          <section className="analytics-section">
            <div className="analytics-heading">
              <div><p className="eyebrow">SIMULATION TRENDS</p><h2>Traffic and emissions over time</h2></div>
              <span>{metricHistory.length ? `Last ${Math.round(metricHistory.at(-1).time_s - metricHistory[0].time_s)} seconds` : 'Collecting data...'}</span>
            </div>
            <div className="analytics-grid">
              <div className="panel chart-panel">
                <MetricChart
                  label="Total estimated CO₂"
                  unit="kg"
                  value={formatNumber(telemetry.total_co2_kg, 2)}
                  data={metricHistory.length ? metricHistory : [telemetry]}
                  dataKey="total_co2_kg"
                  color="#fa8b67"
                />
              </div>
              <div className="panel chart-panel">
                <MetricChart
                  label="Average vehicle wait time"
                  unit="sec"
                  value={formatNumber(telemetry.avg_wait_s)}
                  data={metricHistory.length ? metricHistory : [telemetry]}
                  dataKey="avg_wait_s"
                  color="#66d6b2"
                />
              </div>
            </div>
          </section>
        </div>
        <aside className="insights-column">
          <section className="panel agent-panel">
            <div className="panel-heading">
              <div><p className="eyebrow">TRAFFIC SIGNALS</p><h2>AI signal controller</h2></div>
              <span className={`agent-badge agent-badge-${agentStatus.status}`}>
                <i />{agentStatusLabel(agentStatus.status)}
              </span>
            </div>
            <div className={`agent-status agent-status-${agentStatus.status}`} aria-live="polite">
              <span className="agent-status-indicator" />
              <div>
                <strong>{agentStatus.status === 'active' ? 'Signals controlled automatically' : agentStatusLabel(agentStatus.status)}</strong>
                <span>{agentStatusDescription(agentStatus.status, agentStatus.error)}</span>
              </div>
            </div>
            <div className="agent-decision-row">
              <div><strong>{formatNumber(agentStatus.decisions, 0)}</strong><span>AI signal decisions</span></div>
              <div><strong>{telemetry.traffic_lights.length}</strong><span>intersections monitored</span></div>
            </div>
            <div className="agent-latest-decision">
              <div className="agent-decision-heading">
                <strong>Signal pattern by intersection</strong>
                {agentStatus.last_phases && (
                  <span className={`decision-freshness${agentStatus.status === 'active' ? ' is-live' : ''}`}>
                    {agentStatus.status === 'active' ? 'LATEST' : 'LAST'}
                  </span>
                )}
              </div>
              <p className="agent-phase-note">The system selects a target signal pattern. The current display may differ during a changeover.</p>
              {agentStatus.last_phases && Object.keys(agentStatus.last_phases).length ? (
                <div className="agent-phase-list">
                  {Object.entries(agentStatus.last_phases).map(([junctionId, targetPhase]) => {
                    const light = telemetry.traffic_lights.find((item) => item.id === junctionId)
                    const currentPhase = light?.phase
                    const hasSignalState = typeof light?.state === 'string' && light.state.length > 0
                    const signalCounts = trafficLightSignalCounts(hasSignalState ? light.state : '')
                    return (
                      <div className="agent-phase-row" key={junctionId}>
                        <div className="agent-phase-heading">
                          <strong>{junctionId}</strong>
                          <div className="agent-phase-values">
                            <span><small>Target</small><b>{targetPhase + 1}</b></span>
                            <span><small>Current</small><b>{currentPhase === undefined ? '—' : currentPhase + 1}</b></span>
                          </div>
                        </div>
                        <div className="agent-indication-counts" aria-label={hasSignalState ? `Current indications: ${signalCounts.red} red, ${signalCounts.yellow} yellow, ${signalCounts.green} green` : 'Current signal data unavailable'}>
                          {hasSignalState ? (
                            <>
                              <span className="indication-red"><i />Red <b>{signalCounts.red}</b></span>
                              <span className="indication-yellow"><i />Yellow <b>{signalCounts.yellow}</b></span>
                              <span className="indication-green"><i />Green <b>{signalCounts.green}</b></span>
                            </>
                          ) : <small>Signal data unavailable</small>}
                        </div>
                      </div>
                    )
                  })}
                </div>
              ) : (
                <span className="agent-decision-empty">
                  {agentStatus.status === 'active' ? 'Waiting for the first AI decision.' : 'No automatic signal decisions yet.'}
                </span>
              )}
              <small className="agent-phase-note">Patterns are numbered from 1. Color counts show controlled directions, not the number of traffic lights.</small>
            </div>
          </section>

          <section className="panel signal-panel">
            <div className="panel-heading">
              <div><p className="eyebrow">INTERSECTIONS</p><h2>Current signal colors</h2></div>
              <span className="panel-count">{telemetry.traffic_lights.length} intersections</span>
            </div>
            {telemetry.traffic_lights.length ? (
              <div className="signal-list">
                {telemetry.traffic_lights.map((light) => {
                  const state = typeof light.state === 'string' ? light.state : ''
                  const status = /[yY]/.test(state)
                    ? 'yellow'
                    : /[gG]/.test(state)
                      ? 'green'
                      : /[rR]/.test(state)
                        ? 'red'
                        : 'unknown'
                  return (
                    <div className="signal-row" key={light.id}>
                      <span className={`signal-led signal-led-${status}`} />
                      <strong>{light.id}</strong>
                      <span className={`signal-state signal-state-${status}`}>{signalStatusLabel(status)}</span>
                      <small>Pattern {light.phase + 1}</small>
                    </div>
                  )
                })}
                <p className="signal-panel-note">This summary shows each intersection's overall signal state. Different vehicle movements may have different colors.</p>
              </div>
            ) : <p className="panel-empty">Waiting for traffic signal data...</p>}
          </section>

          <section className="panel hotspot-panel">
            <div className="panel-heading">
              <div><p className="eyebrow">EMISSIONS MAP</p><h2>Highest estimated CO₂</h2></div>
              <span className="panel-count">mg/cell</span>
            </div>
            {hottestCells.length ? (
              <div className="hotspot-list">
                {hottestCells.map((cell, index) => (
                  <div className="hotspot-row" key={cell.id}>
                    <span className="hotspot-rank">0{index + 1}</span>
                    <span className="hotspot-location">Cell {cell.column}, {cell.row}</span>
                    <span className="hotspot-value">{formatNumber(cell.value)} mg</span>
                    <span className="hotspot-bar"><i style={{ width: `${maxPollution ? cell.value / maxPollution * 100 : 0}%` }} /></span>
                  </div>
                ))}
              </div>
            ) : <p className="panel-empty">Estimates appear when the simulation is running.</p>}
          </section>
        </aside>
      </section>

      <footer className="page-footer">
        <span>EcoTwin <i /> SUMO traffic simulation</span>
        <span>Live simulation data <i /> CO₂ values are estimates</span>
      </footer>
    </main>
  )
}

export default App
