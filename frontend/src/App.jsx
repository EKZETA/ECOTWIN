import { useEffect, useMemo, useState } from 'react'
import DeckGL from '@deck.gl/react'
import { COORDINATE_SYSTEM, OrthographicView } from '@deck.gl/core'
import { IconLayer, PathLayer, ScatterplotLayer } from '@deck.gl/layers'
import './App.css'

const API_URL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000'
const WS_URL = import.meta.env.VITE_WS_URL || 'ws://127.0.0.1:8000/ws/telemetry'
const vehicleColors = ['#f07c5d', '#57a6c4', '#e9bd58', '#82b77d', '#a18bc4', '#e8e4d8']
const signalColors = {
  red: '#ff5148',
  yellow: '#ffc247',
  green: '#43d98b',
  unknown: '#536267',
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
}

function App() {
  const [network, setNetwork] = useState(null)
  const [telemetry, setTelemetry] = useState(emptyTelemetry)
  const [isPaused, setIsPaused] = useState(false)
  const [connection, setConnection] = useState('connecting')
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

    const socket = new WebSocket(WS_URL)
    socket.onopen = () => {
      if (active) setConnection('live')
    }
    socket.onmessage = (event) => {
      if (active) setTelemetry(JSON.parse(event.data))
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

    return [
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
  }, [network, telemetry])

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

          <div className="map-label">LIVE STREET VIEW <span>·</span> SUMO CITY GRID</div>
          <div className="legend">
            <span className="legend-road" /> roads
            <span className="legend-car" /> vehicles
            <span className="legend-signal legend-signal-green" /> green
            <span className="legend-signal legend-signal-yellow" /> yellow
            <span className="legend-signal legend-signal-red" /> red
          </div>
        </div>

        <aside className="stats-panel">
          <p className="eyebrow">Live readout</p>
          <div className="stat-grid">
            <div><span>Vehicles</span><strong>{telemetry.active_vehicles}</strong></div>
            <div><span>Avg speed</span><strong>{telemetry.avg_speed_kmh}<small> km/h</small></strong></div>
            <div><span>Avg wait</span><strong>{telemetry.avg_wait_s}<small> sec</small></strong></div>
            <div><span>Total CO2</span><strong>{telemetry.total_co2_kg}<small> kg</small></strong></div>
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
