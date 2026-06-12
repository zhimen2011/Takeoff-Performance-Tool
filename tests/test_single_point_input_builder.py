from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
sys.path.insert(0, str(SRC_DIR))

from stas_app.models.single_point import ATM_MODE_FIXED, SinglePointTakeoffRequest
from stas_app.services.aircraft_registry import AircraftRegistry
from stas_app.services.single_point_input_builder import SinglePointInputBuilder


class SinglePointInputBuilderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = AircraftRegistry.from_directory(ROOT_DIR / "config" / "aircraft")
        self.builder = SinglePointInputBuilder(
            template_dir=ROOT_DIR / "templates",
            airport_file="APTRWY.RWY",
        )

    def test_builds_777f_max_atm_input_with_required_comparison_weight(self) -> None:
        aircraft = self.registry.get("777F")
        request = SinglePointTakeoffRequest(
            aircraft_code="777F",
            airport_code="ZGSZ",
            runway="34L",
            takeoff_weight_kg=290451,
            actual_temperature_c=25,
            wind_kt=0,
            qnh_ref=1013.25,
        )

        content = self.builder.build_atm(request, aircraft)

        self.assertIn("POPT(024) 25000,290451", content)
        self.assertIn("9.E+20\t0\t0\t9.E+20\t9.E+20", content)
        self.assertIn("1\t9.E+20\t15\t", content)
        self.assertIn("XMET(006) 25", content)
        self.assertIn("XMET(001) 25", content)
        self.assertIn("LOAD RUNWAY ZGSZ/34L", content)
        self.assertIn("OUTPUT CLIMIT(044)", content)
        self.assertIn("OUTPUT CLIMIT(026)", content)
        self.assertNotIn("CGIM", content)
        self.assertNotIn("{", content)

    def test_builds_738_fixed_atm_input_with_lower_comparison_weight(self) -> None:
        aircraft = self.registry.get("738")
        request = SinglePointTakeoffRequest(
            aircraft_code="738",
            airport_code="ZBAA",
            runway="18L",
            takeoff_weight_kg=60000,
            actual_temperature_c=20,
            wind_kt=-5,
            qnh_ref=1012,
            flap_setting="10",
            improved_climb=False,
            atm_mode=ATM_MODE_FIXED,
            assumed_temperature_c=50,
        )

        content = self.builder.build_atm(request, aircraft)

        self.assertIn("POPT(024) 20000,60000", content)
        self.assertIn("9.E20     1         0         9.E20", content)
        self.assertIn("1         9.E20     10", content)
        self.assertIn("XMET(006) 20", content)
        self.assertIn("XMET(001) 50", content)
        self.assertIn("XMET(002) -5", content)
        self.assertIn("LOAD RUNWAY ZBAA/18L", content)
        self.assertIn("OUTPUT CLIMIT(026)", content)
        self.assertNotIn("{", content)


if __name__ == "__main__":
    unittest.main()
