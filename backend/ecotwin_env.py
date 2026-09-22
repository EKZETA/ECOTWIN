"""Gymnasium environment for centrally controlling EcoTwin's SUMO signals."""
from __future__ import annotations

import os
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import gymnasium as gym
import numpy as np
import traci
from gymnasium import spaces

from pollution_model import Emission, PollutionGrid
from reward import RewardConfig, calculate_reward


class EcoTwinEnv(gym.Env):
    """A centralised traffic-light controller with local CO₂ hotspot penalties.

    One action selects one permitted green phase for every traffic light. The
    environment advances SUMO for ``decision_interval_steps`` simulation ticks
    (10 seconds with the included 0.5-second SUMO configuration).
    """

    metadata = {"render_modes": []}

    def __init__(
        self,
        *,
        cfg_path: str | os.PathLike[str] | None = None,
        net_path: str | os.PathLike[str] | None = None,
        decision_interval_steps: int = 20,
        episode_steps: int = 180,
        pollution_rows: int = 10,
        pollution_columns: int = 10,
        pollution_threshold_mg: float = 500.0,
        reward_config: RewardConfig = RewardConfig(),
    ) -> None:
        super().__init__()
        if decision_interval_steps <= 0 or episode_steps <= 0:
            raise ValueError("decision_interval_steps and episode_steps must be positive.")

        project_root = Path(__file__).resolve().parents[1]
        self.cfg_path = str(cfg_path or project_root / "simulation" / "configs" / "simulation.sumocfg")
        self.net_path = str(net_path or project_root / "simulation" / "networks" / "city_grid.net.xml")
        self.decision_interval_steps = decision_interval_steps
        self.episode_steps = episode_steps
        self.pollution_threshold_mg = pollution_threshold_mg
        self.reward_config = reward_config
        self.pollution_rows = pollution_rows
        self.pollution_columns = pollution_columns

        # The bundled network has nine signals, each with two green phases.
        # Spaces are finalized against the actual network during reset().
        self.action_space = spaces.MultiDiscrete(np.full(9, 2, dtype=np.int64))
        self.observation_space = spaces.Box(
            low=0,
            high=np.inf,
            shape=(9 * 4 + pollution_rows * pollution_columns,),
            dtype=np.float32,
        )
        self._is_running = False
        self._tls_ids: list[str] = []
        self._green_phases: dict[str, list[int]] = {}
        self._controlled_lanes: dict[str, list[str]] = {}
        self._last_phase: dict[str, int] = {}
        self._episode_step = 0
        self._pollution_grid: PollutionGrid | None = None

    def reset(self, *, seed: int | None = None, options: dict[str, Any] | None = None):
        super().reset(seed=seed)
        self.close()
        traci.start(self._sumo_command())
        self._is_running = True
        self._episode_step = 0
        self._tls_ids = list(traci.trafficlight.getIDList())
        if not self._tls_ids:
            self.close()
            raise RuntimeError("The SUMO network contains no traffic lights.")

        self._green_phases = {tls_id: self._find_green_phases(tls_id) for tls_id in self._tls_ids}
        self._controlled_lanes = {
            tls_id: list(dict.fromkeys(traci.trafficlight.getControlledLanes(tls_id)))
            for tls_id in self._tls_ids
        }
        self._last_phase = {tls_id: traci.trafficlight.getPhase(tls_id) for tls_id in self._tls_ids}
        self._configure_spaces()
        self._pollution_grid = self._build_pollution_grid()
        return self._observation(), self._info(reward_parts={})

    def step(self, action: Iterable[int]):
        if not self._is_running or self._pollution_grid is None:
            raise RuntimeError("Call reset() before step().")
        action_array = np.asarray(action, dtype=np.int64)
        if not self.action_space.contains(action_array):
            raise ValueError(f"Invalid action {action_array.tolist()} for {self.action_space}.")

        phase_switches = self._apply_action(action_array)
        for _ in range(self.decision_interval_steps):
            traci.simulationStep()
            self._pollution_grid.advance(self._vehicle_emissions())

        self._episode_step += 1
        total_wait, total_queue = self._traffic_metrics()
        hotspot_excess = self._pollution_grid.hotspot_excess_mg(self.pollution_threshold_mg)
        reward, reward_parts = calculate_reward(
            total_wait_seconds=total_wait,
            total_queue_vehicles=total_queue,
            co2_hotspot_excess_mg_squared=hotspot_excess,
            phase_switches=phase_switches,
            config=self.reward_config,
        )
        terminated = traci.simulation.getMinExpectedNumber() <= 0
        truncated = self._episode_step >= self.episode_steps
        return self._observation(), reward, terminated, truncated, self._info(reward_parts=reward_parts)

    def close(self) -> None:
        if self._is_running:
            try:
                traci.close()
            finally:
                self._is_running = False

    def _sumo_command(self) -> list[str]:
        return [
            "sumo",
            "-c", self.cfg_path,
            "--no-step-log", "true",
            "--duration-log.disable", "true",
            "--quit-on-end", "false",
        ]

    def _find_green_phases(self, tls_id: str) -> list[int]:
        phases = traci.trafficlight.getAllProgramLogics(tls_id)[0].phases
        green_phases = [index for index, phase in enumerate(phases) if "G" in phase.state and "y" not in phase.state]
        if not green_phases:
            raise RuntimeError(f"Traffic light {tls_id} has no selectable green phase.")
        return green_phases

    def _configure_spaces(self) -> None:
        action_counts = np.array([len(self._green_phases[tls_id]) for tls_id in self._tls_ids], dtype=np.int64)
        self.action_space = spaces.MultiDiscrete(action_counts)
        feature_count = len(self._tls_ids) * 4 + self.pollution_rows * self.pollution_columns
        self.observation_space = spaces.Box(low=0, high=np.inf, shape=(feature_count,), dtype=np.float32)

    def _build_pollution_grid(self) -> PollutionGrid:
        import sumolib

        min_corner, max_corner = sumolib.net.readNet(self.net_path).getBBoxXY()
        return PollutionGrid(
            min_x=min_corner[0], min_y=min_corner[1], max_x=max_corner[0], max_y=max_corner[1],
            rows=self.pollution_rows, columns=self.pollution_columns,
        )

    def _apply_action(self, action: np.ndarray) -> int:
        switches = 0
        for action_index, tls_id in zip(action, self._tls_ids, strict=True):
            target_phase = self._green_phases[tls_id][int(action_index)]
            if target_phase != self._last_phase[tls_id]:
                traci.trafficlight.setPhase(tls_id, target_phase)
                self._last_phase[tls_id] = target_phase
                switches += 1
        return switches

    def _vehicle_emissions(self) -> list[Emission]:
        emissions = []
        step_seconds = traci.simulation.getDeltaT()
        for vehicle_id in traci.vehicle.getIDList():
            x, y = traci.vehicle.getPosition(vehicle_id)
            emissions.append(Emission(x=x, y=y, co2_mg=traci.vehicle.getCO2Emission(vehicle_id) * step_seconds))
        return emissions

    def _traffic_metrics(self) -> tuple[float, int]:
        vehicle_ids = traci.vehicle.getIDList()
        total_wait = sum(traci.vehicle.getWaitingTime(vehicle_id) for vehicle_id in vehicle_ids)
        total_queue = sum(traci.lane.getLastStepHaltingNumber(lane) for lanes in self._controlled_lanes.values() for lane in lanes)
        return total_wait, total_queue

    def _observation(self) -> np.ndarray:
        features: list[float] = []
        for tls_id in self._tls_ids:
            lanes = self._controlled_lanes[tls_id]
            vehicle_count = sum(traci.lane.getLastStepVehicleNumber(lane) for lane in lanes)
            queue_count = sum(traci.lane.getLastStepHaltingNumber(lane) for lane in lanes)
            lane_waits = [traci.vehicle.getWaitingTime(vehicle_id) for lane in lanes for vehicle_id in traci.lane.getLastStepVehicleIDs(lane)]
            average_wait = sum(lane_waits) / len(lane_waits) if lane_waits else 0.0
            features.extend((float(self._last_phase[tls_id]), float(vehicle_count), float(queue_count), average_wait))
        assert self._pollution_grid is not None
        features.extend(self._pollution_grid.values.ravel().tolist())
        return np.asarray(features, dtype=np.float32)

    def _info(self, *, reward_parts: dict[str, float]) -> dict[str, Any]:
        pollution_total = self._pollution_grid.total_co2_mg if self._pollution_grid else 0.0
        hotspot_excess = self._pollution_grid.hotspot_excess_mg(self.pollution_threshold_mg) if self._pollution_grid else 0.0
        return {
            "episode_step": self._episode_step,
            "pollution_total_mg": pollution_total,
            "co2_hotspot_excess_mg_squared": hotspot_excess,
            "reward_parts": reward_parts,
        }
