"""Normalize traffic and pollution features for PPO."""
from __future__ import annotations

import numpy as np


def normalize_observation(
    signal_features: list[float],
    pollution_values: np.ndarray,
    phase_counts: list[int],
) -> np.ndarray:
    signals = np.asarray(signal_features, dtype=np.float32).reshape(-1, 4).copy()
    if len(signals) != len(phase_counts):
        raise ValueError("Traffic-light features and phase counts must have matching lengths.")

    for index, phase_count in enumerate(phase_counts):
        if phase_count <= 0:
            raise ValueError("Every traffic light must have at least one selectable phase.")
        signals[index, 0] /= max(phase_count - 1, 1)
    signals[:, 1] = np.clip(signals[:, 1] / 20.0, 0.0, 1.0)
    signals[:, 2] = np.clip(signals[:, 2] / 20.0, 0.0, 1.0)
    signals[:, 3] = np.clip(signals[:, 3] / 60.0, 0.0, 1.0)
    pollution = np.clip(np.asarray(pollution_values, dtype=np.float32) / 10_000.0, 0.0, 10.0)
    return np.concatenate((signals.ravel(), pollution.ravel())).astype(np.float32, copy=False)
