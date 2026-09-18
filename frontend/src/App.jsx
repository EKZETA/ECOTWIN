import { useEffect, useMemo, useState } from 'react'
import DeckGL from '@deck.gl/react'
import { COORDINATE_SYSTEM, OrthographicView } from '@deck.gl/core'
import { LineLayer, ScatterplotLayer } from '@deck.gl/layers'
import './App.css'

const API_URL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000'
const WS_URL = import.meta.env.VITE_WS_URL || 'ws://127.0.0.1:8000/ws/telemetry'

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
      new LineLayer({
        id: 'city-roads',
        data: network.edges,
        coordinateSystem: COORDINATE_SYSTEM.CARTESIAN,
        getSourcePosition: (edge) => edge.coordinates[0],
        getTargetPosition: (edge) => edge.coordinates[edge.coordinates.length - 1],
        getColor: [92, 111, 121, 220],
        getWidth: 3,
        widthUnits: 'pixels',
      }),
      new ScatterplotLayer({
        id: 'junctions',
        data: network.junctions,
        coordinateSystem: COORDINATE_SYSTEM.CARTESIAN,
        getPosition: (junction) => [junction.x, junction.y],
        getRadius: 5,
        radiusUnits: 'pixels',
        getFillColor: (junction) => junction.has_tls ? [255, 190, 92, 230] : [164, 181, 182, 180],
        pickable: true,
      }),
    ]
  }, [network])

  const liveLayers = useMemo(() => {
    if (!network) return []

    const trafficLights = new Map(telemetry.traffic_lights.map((light) => [light.id, light.state]))
    return [
      new ScatterplotLayer({
        id: 'vehicles',
        data: telemetry.vehicles,
        coordinateSystem: COORDINATE_SYSTEM.CARTESIAN,
        getPosition: (vehicle) => [vehicle.x, vehicle.y],
        getRadius: 6,
        radiusUnits: 'pixels',
        getFillColor: [239, 103, 84, 255],
        getLineColor: [255, 239, 214, 255],
        lineWidthMinPixels: 1,
        stroked: true,
        pickable: true,
      }),
      new ScatterplotLayer({
        id: 'signal-status',
        data: network.junctions.filter((junction) => junction.has_tls),
        coordinateSystem: COORDINATE_SYSTEM.CARTESIAN,
        getPosition: (junction) => [junction.x, junction.y],
        getRadius: 9,
        radiusUnits: 'pixels',
        getFillColor: (junction) => {
          const state = trafficLights.get(junction.id) || ''
          return state.includes('G') ? [88, 196, 132, 100] : [255, 190, 92, 80]
        },
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
              getTooltip={({ object }) => object?.id ? { text: object.id } : null}
            />
          ) : <div className="map-loading">Loading city grid...</div>}

          <div className="map-label">ORTHOGRAPHIC VIEW / CITY GRID</div>
          <div className="legend"><span className="legend-road" /> roads <span className="legend-car" /> vehicles <span className="legend-signal" /> signals</div>
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
