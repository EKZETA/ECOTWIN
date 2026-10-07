import unittest

from backend.traffic_signal_control import safe_transition_phase


class SafeTransitionTests(unittest.TestCase):
    PHASE_STATES = [
        "GGGggrrrrrGGGggrrrrr",
        "yyyyyrrrrryyyyyrrrrr",
        "rrrrrGGGggrrrrrGGGgg",
        "rrrrryyyyyrrrrryyyyy",
    ]

    def test_green_change_uses_the_following_yellow_phase(self):
        self.assertEqual(safe_transition_phase(0, 2, self.PHASE_STATES), 1)
        self.assertEqual(safe_transition_phase(2, 0, self.PHASE_STATES), 3)

    def test_matching_phase_does_not_start_a_transition(self):
        self.assertIsNone(safe_transition_phase(0, 0, self.PHASE_STATES))

    def test_existing_yellow_clearance_is_not_interrupted(self):
        self.assertIsNone(safe_transition_phase(1, 0, self.PHASE_STATES))

    def test_rejects_a_green_change_without_yellow_clearance(self):
        with self.assertRaisesRegex(RuntimeError, "no yellow clearance"):
            safe_transition_phase(0, 2, ["GG", "rr", "GG"])

    def test_rejects_invalid_phase_indexes(self):
        with self.assertRaisesRegex(ValueError, "Invalid target"):
            safe_transition_phase(0, 4, self.PHASE_STATES)


if __name__ == "__main__":
    unittest.main()
