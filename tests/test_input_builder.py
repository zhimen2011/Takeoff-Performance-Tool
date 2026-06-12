from __future__ import annotations

import sys
import unittest
import re
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
sys.path.insert(0, str(SRC_DIR))

from stas_app.models.request import PerformanceRequest
from stas_app.services.aircraft_registry import AircraftRegistry
from stas_app.services.input_builder import StasInputBuilder


class InputBuilderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = AircraftRegistry.from_directory(ROOT_DIR / "config" / "aircraft")
        self.builder = StasInputBuilder(
            template_dir=ROOT_DIR / "templates",
            airport_file="C:/STAS/APTRWY.RWY",
        )

    def test_builds_738_input_with_configured_airport_file(self) -> None:
        aircraft = self.registry.get("738")
        request = PerformanceRequest(
            aircraft_code="738",
            airport_code="ZBAA",
            runways=("18L", "36R"),
            anti_icing="0",
            qnh_ref="1012",
        )

        content = self.builder.build(request, aircraft)

        self.assertIn("AIRPORT FILE C:/STAS/APTRWY.RWY", content)
        self.assertIn("SELECT RUNWAY ZBAA/18L,ZBAA/36R", content)
        self.assertIn("DESCRIBE $QNHREF = 1012$", content)
        self.assertIn("QNHREF = 1012", content)
        self.assertIn("1         30        45        0          9.E20", content)
        self.assertIn("1         9.E20     5         0          0", content)
        self.assertEqual(len(re.findall(r"^\s*CALC\s*$", content, flags=re.MULTILINE)), 1)
        self.assertNotIn("{", content)

    def test_qnhref_describe_can_be_left_empty_without_removing_qnh_parameter(self) -> None:
        aircraft = self.registry.get("738")
        request = PerformanceRequest(
            aircraft_code="738",
            airport_code="ZBAA",
            runways=("18L",),
            anti_icing="0",
            qnh_ref="1012",
            describe_qnh_ref=False,
        )

        content = self.builder.build(request, aircraft)

        self.assertIn("DESCRIBE $$", content)
        self.assertIn("QNHREF = 1012", content)
        self.assertNotIn("DESCRIBE $QNHREF = 1012$", content)
        self.assertNotIn("{", content)

    def test_builds_777f_bump_input(self) -> None:
        aircraft = self.registry.get("777F")
        request = PerformanceRequest(
            aircraft_code="777F",
            airport_code="UNAA",
            anti_icing="0",
            thrust_option="1L1BUMP",
        )

        content = self.builder.build(request, aircraft)

        self.assertIn("RATING = B1L1BUMP", content)
        self.assertIn("SELECT RUNWAY UNAA/*", content)
        self.assertIn("15\t8\t1\t347451\t0", content)
        self.assertNotIn("CGIM", content)
        self.assertNotIn("CALCUATE", content)
        self.assertEqual(content.count("CALCULATE"), 1)
        self.assertNotIn("{", content)

    def test_builds_777f_scenario_with_bleed_anti_ice_runway_and_derate_mapping(self) -> None:
        aircraft = self.registry.get("777F")
        request = PerformanceRequest(
            aircraft_code="777F",
            airport_code="UNAA",
            runway_condition="WET",
            bleed="OFF",
            anti_icing="ENG_WING",
            derate="20%",
        )

        content = self.builder.build(request, aircraft)

        self.assertIn("1\t51\t77\t1\t9.E20", content)
        self.assertIn("15\t8\t1\t347451\t20", content)
        self.assertIn("1\t9.E+20\t15\t2\t3", content)
        self.assertEqual(content.count("CALCULATE"), 1)
        self.assertNotIn("CONF(4)=", content)

    def test_builds_738_scenario_with_contamination_depth(self) -> None:
        aircraft = self.registry.get("738")
        request = PerformanceRequest(
            aircraft_code="738",
            airport_code="ZBAA",
            runway_condition="SLUSH",
            contamination_depth="6.0",
            bleed="OFF",
            anti_icing="ENG_WING_OPT",
            derate="2",
        )

        content = self.builder.build(request, aircraft)

        self.assertIn("1         30        45        3          6", content)
        self.assertIn("15        9.E20     9.E20     79015      2", content)
        self.assertIn("1         9.E20     5         2          7", content)

    def test_contaminated_runway_requires_depth(self) -> None:
        aircraft = self.registry.get("738")
        request = PerformanceRequest(
            aircraft_code="738",
            airport_code="ZBAA",
            runway_condition="SLUSH",
        )

        with self.assertRaisesRegex(ValueError, "contamination_depth"):
            self.builder.build(request, aircraft)

    def test_rejects_unsupported_ice_code_for_738_and_777f(self) -> None:
        request = PerformanceRequest(
            aircraft_code="738",
            airport_code="ZBAA",
            runway_condition="ICE",
        )

        with self.assertRaisesRegex(ValueError, "Unsupported runway_condition"):
            self.builder.build(request, self.registry.get("738"))

    def test_rejects_contamination_depth_outside_current_mm_range(self) -> None:
        request = PerformanceRequest(
            aircraft_code="738",
            airport_code="ZBAA",
            runway_condition="SLUSH",
            contamination_depth="20",
        )

        with self.assertRaisesRegex(ValueError, "outside the supported range"):
            self.builder.build(request, self.registry.get("738"))


if __name__ == "__main__":
    unittest.main()
