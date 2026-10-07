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

if __package__:
    from .pollution_model import Emission, PollutionGrid
    from .rl_observation import normalize_observation
    from .reward import RewardConfig, calculate_reward
    from .traffic_signal_control import safe_transition_phase
else:
    from pollution_model import Emission, PollutionGrid
    from rl_observation import normalize_observation
    from reward import RewardConfig, calculate_reward
    from traffic_signal_control import safe_transition_phase


class EcoTwinEnv(gym.Env):
    """A centralised traffic-light controller with local CO₂ hotspot penalties.

    One action selects a preferred green phase for every traffic light. Phase
    changes pass through the signal program's yellow clearance phase.
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
            high=10,
            shape=(9 * 4 + pollution_rows * pollution_columns,),
            dtype=np.float32,
        )
        self._is_running = False
        self._tls_ids: list[str] = []
        self._green_phases: dict[str, list[int]] = {}
        self._phase_states: dict[str, list[str]] = {}
        self._controlled_lanes: dict[str, list[str]] = {}
        self._target_phase: dict[str, int] = {}
        self._episode_step = 0
        self._sumo_seed: int | None = None
        self._last_wait_seconds = 0.0
        self._last_queue_vehicles = 0
        self._pollution_grid: PollutionGrid | None = None

    def reset(self, *, seed: int | None = None, options: dict[str, Any] | None = None):
        super().reset(seed=seed)
        self.close()
        self._sumo_seed = seed
        traci.start(self._sumo_command())
        self._is_running = True
        self._episode_step = 0
        self._last_wait_seconds = 0.0
        self._last_queue_vehicles = 0
        self._tls_ids = list(traci.trafficlight.getIDList())
        if not self._tls_ids:
            self.close()
            raise RuntimeError("The SUMO network contains no traffic lights.")

        phase_programs = {
            tls_id: traci.trafficlight.getAllProgramLogics(tls_id)[0].phases
            for tls_id in self._tls_ids
        }
        self._phase_states = {
            tls_id: [phase.state for phase in phases]
            for tls_id, phases in phase_programs.items()
        }
        self._green_phases = {
            tls_id: [
                index for index, phase in enumerate(phase_programs[tls_id])
                if "G" in phase.state and "y" not in phase.state
            ]
            for tls_id in self._tls_ids
        }
        if any(not phases for phases in self._green_phases.values()):
            raise RuntimeError("Every controlled traffic light must have a selectable green phase.")
        self._target_phase = {
            tls_id: (
                current_phase
                if (current_phase := traci.trafficlight.getPhase(tls_id))
                in self._green_phases[tls_id]
                else self._green_phases[tls_id][0]
            )
            for tls_id in self._tls_ids
        }
        self._controlled_lanes = {
            tls_id: list(dict.fromkeys(traci.trafficlight.getControlledLanes(tls_id)))
            for tls_id in self._tls_ids
        }
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
        self._last_wait_seconds = total_wait
        self._last_queue_vehicles = total_queue
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
        command = [
            "sumo",
            "-c", self.cfg_path,
            "--no-step-log", "true",
            "--duration-log.disable", "true",
            "--quit-on-end", "false",
        ]
        if self._sumo_seed is not None:
            command.extend(["--seed", str(self._sumo_seed)])
        return command

    def _configure_spaces(self) -> None:
        action_counts = np.array([len(self._green_phases[tls_id]) for tls_id in self._tls_ids], dtype=np.int64)
        self.action_space = spaces.MultiDiscrete(action_counts)
        feature_count = len(self._tls_ids) * 4 + self.pollution_rows * self.pollution_columns
        self.observation_space = spaces.Box(low=0, high=10, shape=(feature_count,), dtype=np.float32)

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
            if target_phase != self._target_phase[tls_id]:
                switches += 1
            transition_phase = safe_transition_phase(
                traci.trafficlight.getPhase(tls_id),
                target_phase,
                self._phase_states[tls_id],
            )
            if transition_phase is not None:
                traci.trafficlight.setPhase(tls_id, transition_phase)
            self._target_phase[tls_id] = target_phase
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
            green_phases = self._green_phases[tls_id]
            phase_index = green_phases.index(self._target_phase[tls_id])
            features.extend((float(phase_index), float(vehicle_count), float(queue_count), average_wait))
        assert self._pollution_grid is not None
        return normalize_observation(
            features,
            self._pollution_grid.values,
            [len(self._green_phases[tls_id]) for tls_id in self._tls_ids],
        )

    def _info(self, *, reward_parts: dict[str, float]) -> dict[str, Any]:
        pollution_total = self._pollution_grid.total_co2_mg if self._pollution_grid else 0.0
        hotspot_excess = self._pollution_grid.hotspot_excess_mg(self.pollution_threshold_mg) if self._pollution_grid else 0.0
        return {
            "episode_step": self._episode_step,
            "pollution_total_mg": pollution_total,
            "co2_hotspot_excess_mg_squared": hotspot_excess,
            "wait_seconds": self._last_wait_seconds if self._episode_step else 0.0,
            "queue_vehicles": self._last_queue_vehicles if self._episode_step else 0,
            "reward_parts": reward_parts,
        }
