import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from reward import RewardConfig, calculate_reward


class RewardTests(unittest.TestCase):
    def test_reward_is_negative_weighted_penalty(self):
        reward, parts = calculate_reward(
            total_wait_seconds=100,
            total_queue_vehicles=10,
            co2_hotspot_excess_mg_squared=100_000,
            phase_switches=3,
        )
        self.assertLess(reward, 0)
        self.assertAlmostEqual(reward, -parts["total_penalty"])

    def test_larger_hotspot_produces_lower_reward(self):
        common = {"total_wait_seconds": 0, "total_queue_vehicles": 0, "phase_switches": 0}
        low_reward, _ = calculate_reward(co2_hotspot_excess_mg_squared=1, **common)
        high_reward, _ = calculate_reward(co2_hotspot_excess_mg_squared=1_000_000, **common)
        self.assertLess(high_reward, low_reward)

    def test_rejects_invalid_metrics_and_scales(self):
        with self.assertRaises(ValueError):
            calculate_reward(total_wait_seconds=-1, total_queue_vehicles=0, co2_hotspot_excess_mg_squared=0, phase_switches=0)
        with self.assertRaises(ValueError):
            calculate_reward(
                total_wait_seconds=0, total_queue_vehicles=0, co2_hotspot_excess_mg_squared=0, phase_switches=0,
                config=RewardConfig(wait_scale_seconds=0),
            )


if __name__ == "__main__":
    unittest.main()
