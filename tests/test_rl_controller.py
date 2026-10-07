import sys
import tempfile
import unittest
from pathlib import Path

import gymnasium as gym
import numpy as np
import torch
from ray.rllib.core.columns import Columns

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from rl_controller import RLAgentController, deterministic_action


class FakeModule:
    action_space = gym.spaces.MultiDiscrete(np.array([2, 3, 2]))

    def __init__(self, logits):
        self.logits = torch.tensor([logits], dtype=torch.float32)

    def forward_inference(self, inputs):
        return {Columns.ACTION_DIST_INPUTS: self.logits}


class FakeAlgorithm:
    def __init__(self, module):
        self.module = module

    def get_module(self):
        return self.module


class RLControllerTests(unittest.TestCase):
    def test_deterministic_action_selects_each_multidiscrete_argmax(self):
        algorithm = FakeAlgorithm(FakeModule([1, 4, 3, 2, 0, 1, 5]))
        self.assertEqual(deterministic_action(algorithm, np.zeros(1)), [1, 0, 1])

    def test_deterministic_action_rejects_incompatible_logits(self):
        algorithm = FakeAlgorithm(FakeModule([1, 4, 3]))
        with self.assertRaises(RuntimeError):
            deterministic_action(algorithm, np.zeros(1))

    def test_missing_checkpoint_is_reported_in_status(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            controller = RLAgentController(Path(temp_dir) / "missing")
            controller.load()
            self.assertEqual(controller.status()["status"], "missing_checkpoint")
            self.assertIn("No RLlib checkpoint", controller.status()["error"])


if __name__ == "__main__":
    unittest.main()
