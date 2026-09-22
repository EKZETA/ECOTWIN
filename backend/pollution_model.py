"""Spatial CO₂ accumulation model used by the EcoTwin RL environment.

The model is intentionally deterministic and independent from TraCI, so its
behaviour can be tested before it is connected to a live SUMO simulation.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Emission:
    """An amount of CO₂ emitted at one SUMO Cartesian coordinate, in mg."""

    x: float
    y: float
    co2_mg: float


class PollutionGrid:
    """Accumulate, decay, and diffuse CO₂ over a rectangular city grid.

    ``retention`` controls how much prior pollution remains per simulation
    update. ``diffusion`` is the fraction of each cell spread equally to its
    orthogonal neighbours after emissions are added. Neither operation creates
    or destroys pollution beyond the configured retention loss.
    """

    def __init__(
        self,
        *,
        min_x: float,
        min_y: float,
        max_x: float,
        max_y: float,
        rows: int = 10,
        columns: int = 10,
        retention: float = 0.97,
        diffusion: float = 0.02,
    ) -> None:
        if max_x <= min_x or max_y <= min_y:
            raise ValueError("Grid bounds must have a positive area.")
        if rows <= 0 or columns <= 0:
            raise ValueError("rows and columns must be positive.")
        if not 0 <= retention <= 1:
            raise ValueError("retention must be between 0 and 1.")
        if not 0 <= diffusion <= 1:
            raise ValueError("diffusion must be between 0 and 1.")

        self.min_x = min_x
        self.min_y = min_y
        self.max_x = max_x
        self.max_y = max_y
        self.rows = rows
        self.columns = columns
        self.retention = retention
        self.diffusion = diffusion
        self._values = np.zeros((rows, columns), dtype=np.float64)

    @property
    def values(self) -> np.ndarray:
        """Return a read-only snapshot of concentrations in mg per cell."""
        snapshot = self._values.copy()
        snapshot.flags.writeable = False
        return snapshot

    @property
    def total_co2_mg(self) -> float:
        return float(self._values.sum())

    def reset(self) -> None:
        self._values.fill(0)

    def cell_for_position(self, x: float, y: float) -> tuple[int, int]:
        """Return the grid cell containing a position, clamped to its bounds."""
        column = int((x - self.min_x) / (self.max_x - self.min_x) * self.columns)
        row = int((y - self.min_y) / (self.max_y - self.min_y) * self.rows)
        return (
            min(self.rows - 1, max(0, row)),
            min(self.columns - 1, max(0, column)),
        )

    def advance(self, emissions: Iterable[Emission]) -> np.ndarray:
        """Advance one model interval and return the resulting grid snapshot."""
        next_values = self._values * self.retention
        for emission in emissions:
            if emission.co2_mg < 0:
                raise ValueError("CO₂ emissions cannot be negative.")
            row, column = self.cell_for_position(emission.x, emission.y)
            next_values[row, column] += emission.co2_mg

        self._values = self._diffuse(next_values)
        return self.values

    def hotspot_excess_mg(self, threshold_mg: float) -> float:
        """Return squared excess above a per-cell threshold for reward shaping."""
        if threshold_mg < 0:
            raise ValueError("threshold_mg cannot be negative.")
        excess = np.maximum(0, self._values - threshold_mg)
        return float(np.square(excess).sum())

    def _diffuse(self, source: np.ndarray) -> np.ndarray:
        if self.diffusion == 0:
            return source

        result = source * (1 - self.diffusion)
        for row in range(self.rows):
            for column in range(self.columns):
                neighbours = self._neighbours(row, column)
                if neighbours:
                    share = source[row, column] * self.diffusion / len(neighbours)
                    for neighbour_row, neighbour_column in neighbours:
                        result[neighbour_row, neighbour_column] += share
        return result

    def _neighbours(self, row: int, column: int) -> list[tuple[int, int]]:
        candidates = ((row - 1, column), (row + 1, column), (row, column - 1), (row, column + 1))
        return [
            (neighbour_row, neighbour_column)
            for neighbour_row, neighbour_column in candidates
            if 0 <= neighbour_row < self.rows and 0 <= neighbour_column < self.columns
        ]
