import os
import sys
import threading
from typing import Dict, Any, List, Optional
import traci
import sumolib

sumo_home = os.environ.get("SUMO_HOME", r"C:\Program Files (x86)\Eclipse\Sumo")
os.environ["SUMO_HOME"] = sumo_home
tools = os.path.join(sumo_home, "tools")
if tools not in sys.path:
    sys.path.append(tools)

class SumoSimulationRunner:
    def __init__(self, cfg_path: Optional[str] = None, use_gui: bool = True):
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        env_cfg = os.environ.get("SIMULATION_PATH")
        env_net = os.environ.get("NETWORK_PATH")

        self.cfg_path = cfg_path or (env_cfg if env_cfg else os.path.join(base_dir, "simulation", "configs", "simulation.sumocfg"))
        self.net_path = env_net if env_net else os.path.join(base_dir, "simulation", "networks", "city_grid.net.xml")
        self.use_gui = use_gui
        self.is_running = False
        self.is_paused = False
        self.step_count = 0
        self.sim_time = 0.0

        self.total_co2_mg = 0.0
        self.peak_vehicles = 0
        self.total_wait_seconds = 0.0

        self.tls_ids: List[str] = []
        self._lock = threading.Lock()
        self._network_cache: Optional[Dict[str, Any]] = None

    def start(self, use_gui: Optional[bool] = None):
        with self._lock:
            self._start_unlocked(use_gui)

    def _start_unlocked(self, use_gui: Optional[bool] = None):
        """Start SUMO while ``self._lock`` is already held."""
        if self.is_running:
            self._close_unlocked()

        gui = self.use_gui if use_gui is None else use_gui
        bin_name = "sumo-gui.exe" if gui else "sumo.exe"
        sumo_bin = os.path.join(sumo_home, "bin", bin_name)
        if not os.path.exists(sumo_bin):
            sumo_bin = "sumo-gui" if gui else "sumo"

        sumo_cmd = [
            sumo_bin,
            "-c", self.cfg_path,
            "--no-step-log", "true",
            "--duration-log.disable", "true",
            "--quit-on-end", "false"
        ]
        if gui:
            # --start tells SUMO-GUI to begin immediately without waiting for manual Play button press
            sumo_cmd.append("--start")

        traci.start(sumo_cmd)
        self.tls_ids = list(traci.trafficlight.getIDList())
        self.is_running = True
        self.is_paused = False
        self.step_count = 0
        self.sim_time = 0.0
        self.total_co2_mg = 0.0
        self.total_wait_seconds = 0.0
        self.peak_vehicles = 0

    def step(self) -> Dict[str, Any]:
        with self._lock:
            if not self.is_running:
                self._start_unlocked()

            traci.simulationStep()
            self.step_count += 1
            self.sim_time = traci.simulation.getTime()

            vehicle_ids = traci.vehicle.getIDList()
            n_vehicles = len(vehicle_ids)
            if n_vehicles > self.peak_vehicles:
                self.peak_vehicles = n_vehicles

            step_co2_mg = 0.0
            step_wait_time = 0.0
            total_speed_ms = 0.0
            vehicles_data = []

            for vid in vehicle_ids:
                co2_rate = traci.vehicle.getCO2Emission(vid) #mg/s
                speed = traci.vehicle.getSpeed(vid)            # m/s
                pos = traci.vehicle.getPosition(vid)           # (x, y)
                angle = traci.vehicle.getAngle(vid)            # heading degrees
                wait = traci.vehicle.getWaitingTime(vid)       # seconds
                vtype = traci.vehicle.getTypeID(vid)

                #step length is 0.5s

                step_co2_mg += (co2_rate * 0.5)
                step_wait_time += wait
                total_speed_ms += speed

                vehicles_data.append({
                    "id": vid,
                    "type": vtype,
                    "x": round(pos[0], 2),
                    "y": round(pos[1], 2),
                    "speed_kmh": round(speed * 3.6, 1),
                    "angle": round(angle, 1),
                    "co2_mg_s": round(co2_rate, 1),
                    "wait_s": round(wait, 1)
                })

            self.total_co2_mg += step_co2_mg
            self.total_wait_seconds += (step_wait_time * 0.5)

            tls_data = []
            for tid in self.tls_ids:
                tls_data.append({
                    "id":tid,
                    "state": traci.trafficlight.getRedYellowGreenState(tid),
                    "phase": traci.trafficlight.getPhase(tid)
                })

            avg_speed_kmh = round((total_speed_ms / n_vehicles * 3.6), 1) if n_vehicles > 0 else 0.0
            avg_wait_s = round(step_wait_time / n_vehicles, 1) if n_vehicles > 0 else 0.0

            return{
                "step": self.step_count,
                "time_s": round(self.sim_time, 1),
                "active_vehicles": n_vehicles,
                "peak_vehicles": self.peak_vehicles,
                "step_co2_g": round(step_co2_mg / 1000.0, 3),
                "total_co2_kg": round(self.total_co2_mg / 1e6, 4),
                "avg_speed_kmh": avg_speed_kmh,
                "avg_wait_s": avg_wait_s,
                "vehicles": vehicles_data,
                "traffic_lights": tls_data
            }

    def set_tls_phase(self, tls_id: str, phase_index: int):
        with self._lock:
            if self.is_running and tls_id in self.tls_ids:
                traci.trafficlight.setPhase(tls_id, phase_index)

    def close(self):
        with self._lock:
            self._close_unlocked()

    def _close_unlocked(self):
        """Close SUMO while ``self._lock`` is already held."""
        if self.is_running:
            try:
                traci.close()
            except Exception:
                pass
            self.is_running = False

    def get_network_geometry(self) -> Dict[str, Any]:
        if self._network_cache is not None:
            return self._network_cache

        net = sumolib.net.readNet(self.net_path)
        bbox = net.getBBoxXY()

        edges_data = []
        for edge in net.getEdges():
            if edge.getFunction() == "internal":
                continue
            shape = edge.getShape()
            edges_data.append({
                "id": edge.getID(),
                "lanes": edge.getLaneNumber(),
                "speed": edge.getSpeed(),
                "coordinates": [[round(p[0], 2), round(p[1], 2)] for p in shape]
            })

        junctions_data = []
        for node in net.getNodes():
            coord = node.getCoord()
            junctions_data.append({
                "id": node.getID(),
                "type": node.getType(),
                "x": round(coord[0], 2),
                "y": round(coord[1], 2),
                "has_tls": node.getID() in self.tls_ids or node.getType() == "traffic_light"
            })
        self._network_cache = {
            "bbox": {"min_x": bbox[0][0], "min_y": bbox[0][1], "max_x": bbox[1][0], "max_y": bbox[1][1]},
            "edges": edges_data,
            "junctions": junctions_data,
            "traffic_light_ids": self.tls_ids or [j["id"] for j in junctions_data if j["has_tls"]]
        }
        return self._network_cache
