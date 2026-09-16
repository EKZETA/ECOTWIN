# City Grid Monitor

A beginner-friendly React frontend for the SUMO simulation in this repository. It uses Deck.gl to draw the SUMO city grid and listens for live vehicle telemetry from FastAPI.

## 1. Start the backend

Open PowerShell in the project root (`Project 1`) and make sure Python dependencies are installed:

```powershell
python -m pip install -r requirements.txt
```

SUMO must also be installed. The backend currently looks for SUMO in:

```text
C:\Program Files (x86)\Eclipse\Sumo
```

If SUMO is installed somewhere else, set `SUMO_HOME` before starting the backend:

```powershell
$env:SUMO_HOME = 'C:\path\to\sumo'
```

Start FastAPI:

```powershell
python -m uvicorn backend.main:app --reload --port 8000
```

The backend will be available at `http://localhost:8000`. The interactive API page is at `http://localhost:8000/docs`.

## 2. Start the frontend

Open a second PowerShell window in `frontend`:

```powershell
npm install
npm run dev
```

Open the URL printed by Vite, normally `http://localhost:5173`.

During local development, Vite proxies `/api` and `/ws` to the backend on port 8000. This avoids browser `localhost` IPv4/IPv6 connection issues. To use a different backend URL, create `frontend/.env`:

```text
VITE_API_URL=http://localhost:8000
```

Restart Vite after changing `.env`.

## 3. How the connection works

1. React calls `GET /api/network` once. FastAPI reads `simulation/networks/city_grid.net.xml` and returns road and junction coordinates.
2. React opens `ws://localhost:8000/ws/telemetry`. The backend starts the SUMO simulation and sends telemetry frames repeatedly.
3. Deck.gl draws roads with `LineLayer`, junctions with `ScatterplotLayer`, and moving vehicles with another `ScatterplotLayer`.
4. The Pause and Reset buttons call the backend endpoints under `/api/simulation/...`.

The map uses Deck.gl's `OrthographicView` because SUMO coordinates are local X/Y metres, not latitude/longitude. This is a city-grid view, so no map token or external tile service is required.

## Useful commands

From `frontend`:

```powershell
npm run dev       # development server with hot reload
npm run build     # production build check
npm run lint      # lint the React code
npm run preview   # preview the production build
```

If the page says that telemetry is offline, check that the FastAPI terminal is still running and that SUMO can be launched. The browser must be opened through Vite, not by double-clicking `index.html`.
