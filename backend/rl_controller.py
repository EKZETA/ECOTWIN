"""Load and run the trained traffic-signal policy."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

if __package__:
    from .ecotwin_env import EcoTwinEnv
    from .reward import RewardConfig
else:
    from ecotwin_env import EcoTwinEnv
    from reward import RewardConfig


def deterministic_action(algorithm, observation) -> list[int]:
    import torch
    from ray.rllib.core.columns import Columns

    module = algorithm.get_module()
    with torch.inference_mode():
        output = module.forward_inference({
            Columns.OBS: torch.as_tensor(observation, dtype=torch.float32).unsqueeze(0),
        })

    distribution_inputs = output.get(Columns.ACTION_DIST_INPUTS)
    action_space = module.action_space
    if distribution_inputs is None or not hasattr(action_space, "nvec"):
        raise RuntimeError("The checkpoint does not expose a MultiDiscrete PPO action distribution.")

    logits = distribution_inputs.squeeze(0)
    action_sizes = [int(size) for size in action_space.nvec]
    if logits.numel() != sum(action_sizes):
        raise RuntimeError(
            f"Policy output has {logits.numel()} logits, expected {sum(action_sizes)} "
            "for the traffic-light action space."
        )

    action = []
    offset = 0
    for size in action_sizes:
        action.append(int(torch.argmax(logits[offset:offset + size]).item()))
        offset += size
    return action


def env_creator(env_config: dict[str, Any]) -> EcoTwinEnv:
    return EcoTwinEnv(
        cfg_path=env_config.get("cfg_path"),
        net_path=env_config.get("net_path"),
        decision_interval_steps=env_config.get("decision_interval_steps", 10),
        episode_steps=env_config.get("episode_steps", 40),
        pollution_rows=env_config.get("pollution_rows", 10),
        pollution_columns=env_config.get("pollution_columns", 10),
        pollution_threshold_mg=env_config.get("pollution_threshold_mg", 500.0),
        reward_config=RewardConfig(),
    )


class RLAgentController:
    def __init__(self, checkpoint_path: str | Path):
        self.checkpoint_path = Path(checkpoint_path).resolve()
        self._algorithm = None
        self._owns_ray = False
        self._status = "not_loaded"
        self._error: str | None = None
        self.decisions = 0
        self.last_action: list[int] | None = None
        self.last_phases: dict[str, int] | None = None

    @property
    def is_active(self) -> bool:
        return self._status == "active"

    def status(self) -> dict[str, Any]:
        return {
            "status": self._status,
            "checkpoint": str(self.checkpoint_path),
            "decisions": self.decisions,
            "last_action": self.last_action,
            "last_phases": self.last_phases,
            "error": self._error,
        }

    def load(self) -> None:
        if not self.checkpoint_path.is_dir() or not (self.checkpoint_path / "rllib_checkpoint.json").is_file():
            self._status = "missing_checkpoint"
            self._error = f"No RLlib checkpoint found at {self.checkpoint_path}"
            logging.error(self._error)
            return

        try:
            import ray
            from ray.rllib.algorithms.algorithm import Algorithm
            from ray.tune.registry import register_env

            register_env("ecotwin-v0", env_creator)
            if not ray.is_initialized():
                ray.init(ignore_reinit_error=True, include_dashboard=False)
                self._owns_ray = True
            self._algorithm = Algorithm.from_checkpoint(str(self.checkpoint_path))
            self._status = "active"
            self._error = None
            logging.info("Loaded RL policy checkpoint from %s", self.checkpoint_path)
        except Exception as exc:
            self._status = "load_failed"
            self._error = str(exc)
            logging.exception("Could not load RL policy checkpoint from %s", self.checkpoint_path)
            self.close()

    def act(self, observation) -> list[int]:
        if not self.is_active or self._algorithm is None:
            raise RuntimeError(f"RL policy is not active: {self._status}")
        try:
            action_list = deterministic_action(self._algorithm, observation)
            self.decisions += 1
            self.last_action = action_list
            return action_list
        except Exception as exc:
            self._status = "runtime_error"
            self._error = str(exc)
            logging.exception("RL policy inference failed")
            raise

    def record_phases(self, phases: dict[str, int]) -> None:
        self.last_phases = phases

    def close(self) -> None:
        if self._algorithm is not None:
            self._algorithm.stop()
            self._algorithm = None
        if self._owns_ray:
            import ray

            ray.shutdown()
            self._owns_ray = False
