"""
main.py: FastAPI Application & WebSocket Telemetry Server
Streams live simulation frames (vehicles, CO2, traffic lights) in real-time.
"""
import asyncio
import json
from contextlib import asynccontextmanager
from typing import Set, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from backend.sumo_runner import SumoSimulationRunner

runner = SumoSimulationRunner()
connected_clients: Set[WebSocket] = set()
sim_task: Optional[asyncio.Task] = None
is_streaming = False
sim_fps = 10

async def simulation_loop():
    global is_streaming
    runner.start()
    is_streaming = True
    print("Simulation background loop started.")

    try:
        while is_streaming:
            if not runner.is_paused:
                telemetry = runner.step()
                if connected_clients:
                    payload = json.dumps(telemetry)
                    dead_clients = set()
                    for ws in connected_clients:
                        try:
                            await ws.send_text(payload)
                        except Exception:
                            dead_clients.add(ws)
                    for ws in dead_clients:
                        connected_clients.remove(ws)

            await asyncio.sleep(1.0 / sim_fps)

    except asyncio.CancelledError:
        print("Simulation Loop Cancelled.")

    finally:
        runner.close()
        is_streaming = False
        print("Simulation loop stopped.")

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    global is_streaming, sim_task
    is_streaming = False
    if sim_task:
        sim_task.cancel()
    runner.close()

app = FastAPI(
    title="EcoTwin Telemetry API",
    description="Real-time SUMO TraCI & Carbon Dispersal API Gateway",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {
        "project": "EcoTwin: RL for Urban Carbon Dispersal",
        "status": "online",
        "simulation_running": runner.is_running,
        "is_paused": runner.is_paused,
        "step": runner.step_count,
        "sim_time": runner.sim_time,
        "active_clients": len(connected_clients)
    }

@app.get("/api/network")
def get_network():
    return runner.get_network_geometry()

@app.post("/api/simulation/start")
async def start_simulation():
    global sim_task, is_streaming
    if is_streaming and sim_task and not sim_task.done():
        runner.is_paused = False
        return {"status": "resumed", "step": runner.step_count}

    sim_task = asyncio.create_task(simulation_loop())
    return {"status": "started"}

@app.post("/api/simulation/pause")
def pause_simulation():
    runner.is_paused = not runner.is_paused
    return {"status": "paused" if runner.is_paused else "running"}

@app.post("/api/simulation/reset")
async def reset_simulation():
    global sim_task, is_streaming
    is_streaming = False
    if sim_task:
        sim_task.cancel()
        try:
            await sim_task
        except asyncio.CancelledError:
            pass
    runner.close()
    sim_task = asyncio.create_task(simulation_loop())
    return {"status": "reset_and_restarted"}

class PhaseControlRequest(BaseModel):
    tls_id: str
    phase_index: int

@app.post("/api/simulation/set_phase")
def set_phase(req: PhaseControlRequest):
    runner.set_tls_phase(req.tls_id, req.phase_index)
    return {"status": "phase_updated", "tls_id": req.tls_id, "phase": req.phase_index}

@app.websocket("/ws/telemetry")
async def websocket_telemetry_endpoint(websocket: WebSocket):
    global sim_task, is_streaming, sim_fps
    await websocket.accept()
    connected_clients.add(websocket)
    print(f"WebSocket client connected. Total clients: {len(connected_clients)}")

    if not is_streaming or sim_task is None or sim_task.done():
        sim_task = asyncio.create_task(simulation_loop())

    try:
        while True:
            message = await websocket.receive_text()
            data = json.loads(message)
            action = data.get("action")
            if action == "pause":
                runner.is_paused = True
            elif action == "resume":
                runner.is_paused = False
            elif action == "speed":
                sim_fps = max(1, min(60, int(data.get("fps", 10))))
            elif action == "set_phase":
                runner.set_tls_phase(data.get("tls_id"), int(data.get("phase", 0)))
    except WebSocketDisconnect:
        connected_clients.remove(websocket)
        print(f"Client disconnected. Remaining: {len(connected_clients)}")
    except Exception as e:
        if websocket in connected_clients:
            connected_clients.remove(websocket)
        print(f"WebSocket error: {e}")
