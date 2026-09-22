"""Multi-objective reward calculation for EcoTwin traffic-control policies."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RewardConfig:
    """Weights and scales for terms that are minimized by the policy."""

    wait_weight: float = 0.40
    co2_weight: float = 0.35
    queue_weight: float = 0.15
    phase_switch_weight: float = 0.10
    wait_scale_seconds: float = 1_000.0
    co2_scale_mg_squared: float = 1_000_000.0
    queue_scale_vehicles: float = 100.0
    phase_switch_scale: float = 9.0


def calculate_reward(
    *,
    total_wait_seconds: float,
    total_queue_vehicles: int,
    co2_hotspot_excess_mg_squared: float,
    phase_switches: int,
    config: RewardConfig = RewardConfig(),
) -> tuple[float, dict[str, float]]:
    """Return a reward and observable, normalized penalty components.

    CO₂ hotspot excess is squared by ``PollutionGrid.hotspot_excess_mg``. This
    makes dangerous local accumulation cost substantially more than evenly
    distributed low-level emissions.
    """
    metrics = {
        "wait": total_wait_seconds,
        "queue": float(total_queue_vehicles),
        "co2_hotspot": co2_hotspot_excess_mg_squared,
        "phase_switches": float(phase_switches),
    }
    if any(value < 0 for value in metrics.values()):
        raise ValueError("Reward metrics cannot be negative.")

    scales = (
        config.wait_scale_seconds,
        config.co2_scale_mg_squared,
        config.queue_scale_vehicles,
        config.phase_switch_scale,
    )
    if any(scale <= 0 for scale in scales):
        raise ValueError("Reward scales must be positive.")

    components = {
        "wait_penalty": config.wait_weight * total_wait_seconds / config.wait_scale_seconds,
        "co2_hotspot_penalty": config.co2_weight * co2_hotspot_excess_mg_squared / config.co2_scale_mg_squared,
        "queue_penalty": config.queue_weight * total_queue_vehicles / config.queue_scale_vehicles,
        "phase_switch_penalty": config.phase_switch_weight * phase_switches / config.phase_switch_scale,
    }
    total_penalty = sum(components.values())
    return -total_penalty, {**components, "total_penalty": total_penalty}
