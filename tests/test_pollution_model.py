import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from pollution_model import Emission, PollutionGrid


class PollutionGridTests(unittest.TestCase):
    def make_grid(self, **overrides):
        settings = {
            "min_x": 0,
            "min_y": 0,
            "max_x": 100,
            "max_y": 100,
            "rows": 2,
            "columns": 2,
            "retention": 1,
            "diffusion": 0,
        }
        settings.update(overrides)
        return PollutionGrid(**settings)

    def test_maps_boundary_coordinates_to_valid_cells(self):
        grid = self.make_grid()
        self.assertEqual(grid.cell_for_position(0, 0), (0, 0))
        self.assertEqual(grid.cell_for_position(100, 100), (1, 1))
        self.assertEqual(grid.cell_for_position(-10, 120), (1, 0))

    def test_accumulates_emissions_in_the_correct_cell(self):
        grid = self.make_grid()
        values = grid.advance([Emission(x=10, y=10, co2_mg=25)])
        self.assertEqual(values[0, 0], 25)
        self.assertEqual(grid.total_co2_mg, 25)

    def test_retention_reduces_existing_pollution(self):
        grid = self.make_grid(retention=0.8)
        grid.advance([Emission(x=10, y=10, co2_mg=100)])
        grid.advance([])
        self.assertAlmostEqual(grid.total_co2_mg, 80)

    def test_diffusion_preserves_total_pollution(self):
        grid = self.make_grid(diffusion=0.4)
        values = grid.advance([Emission(x=10, y=10, co2_mg=100)])
        self.assertAlmostEqual(values.sum(), 100)
        self.assertAlmostEqual(values[0, 0], 60)
        self.assertAlmostEqual(values[0, 1], 20)
        self.assertAlmostEqual(values[1, 0], 20)

    def test_hotspot_penalty_only_counts_excess(self):
        grid = self.make_grid()
        grid.advance([Emission(x=10, y=10, co2_mg=15)])
        self.assertEqual(grid.hotspot_excess_mg(10), 25)


if __name__ == "__main__":
    unittest.main()
