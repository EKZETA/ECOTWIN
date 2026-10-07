import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from rl_observation import normalize_observation


class RLObservationTests(unittest.TestCase):
    def test_normalizes_signal_and_pollution_features(self):
        observation = normalize_observation(
            [1, 40, 10, 120, 0, 5, 2, 30],
            np.array([[0, 10_000], [100_000, 200_000]], dtype=np.float32),
            [2, 1],
        )
        np.testing.assert_allclose(
            observation,
            [1, 1, 0.5, 1, 0, 0.25, 0.1, 0.5, 0, 1, 10, 10],
        )

    def test_rejects_mismatched_signal_and_phase_counts(self):
        with self.assertRaises(ValueError):
            normalize_observation([0, 0, 0, 0], np.zeros((1, 1)), [2, 2])


if __name__ == "__main__":
    unittest.main()
