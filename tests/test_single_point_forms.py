from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
sys.path.insert(0, str(SRC_DIR))

from stas_app.models.single_point import (
    SinglePointCalculationResult,
    SinglePointSectionResult,
    SinglePointTakeoffRequest,
)
from stas_app.services.single_point_service import ATM_WEIGHT_MISMATCH_NOTICE
from stas_app.ui.single_point_forms import format_single_point_result, format_single_point_runway_distance


class SinglePointFormsTests(unittest.TestCase):
    def test_formats_runway_distance_values(self) -> None:
        result = SinglePointCalculationResult(
            status="success",
            request=SinglePointTakeoffRequest(
                aircraft_code="738",
                airport_code="ZBAA",
                runway="18L",
                takeoff_weight_kg=60000,
                actual_temperature_c=25,
                wind_kt=0,
            ),
            full=SinglePointSectionResult(
                label="FULL",
                ae_go_m=1631,
                eo_go_m=3230,
                accel_stop_m=3346,
                tora_m=3000,
                toda_m=3260,
                asda_m=3000,
                slope_percent=0.25,
            ),
        )

        text = format_single_point_runway_distance(result, "FULL")

        self.assertIn("Runway Distance", text)
        self.assertIn("AE-GO: 1631 M", text)
        self.assertIn("EO-GO: 3230 M", text)
        self.assertIn("ACCEL-STOP: 3346 M", text)
        self.assertIn("TORA: 3000 M", text)
        self.assertIn("TODA: 3260 M", text)
        self.assertIn("ASDA: 3000 M", text)
        self.assertIn("SLOPE: 0.25%", text)

    def test_formats_738_vref_and_accel_height_units(self) -> None:
        result = SinglePointCalculationResult(
            status="success",
            request=SinglePointTakeoffRequest(
                aircraft_code="738",
                airport_code="ZBAA",
                runway="18L",
                takeoff_weight_kg=60000,
                actual_temperature_c=25,
                wind_kt=0,
            ),
            full=SinglePointSectionResult(label="FULL", vref30=141, accel_height_ft=400),
        )

        text = format_single_point_result(result, "FULL")

        self.assertIn("VREF: 141 KT", text)
        self.assertNotIn("VREF30", text)
        self.assertIn("ACCEL HT: 400 ft AGL", text)

    def test_formats_777f_vref30_label(self) -> None:
        result = SinglePointCalculationResult(
            status="success",
            request=SinglePointTakeoffRequest(
                aircraft_code="777F",
                airport_code="ZBAA",
                runway="18L",
                takeoff_weight_kg=190000,
                actual_temperature_c=25,
                wind_kt=0,
            ),
            full=SinglePointSectionResult(label="FULL", vref30=155, accel_height_ft=400),
        )

        text = format_single_point_result(result, "FULL")

        self.assertIn("VREF30: 155 KT", text)

    def test_formats_atm_notice_first_and_uses_section_takeoff_weight(self) -> None:
        result = SinglePointCalculationResult(
            status="success",
            request=SinglePointTakeoffRequest(
                aircraft_code="777F",
                airport_code="ZBAA",
                runway="18L",
                takeoff_weight_kg=60000,
                actual_temperature_c=25,
                wind_kt=0,
            ),
            atm=SinglePointSectionResult(
                label="ATM",
                takeoff_weight_kg=59000,
                notice=ATM_WEIGHT_MISMATCH_NOTICE,
                vref30=155,
                accel_height_ft=400,
            ),
        )

        text = format_single_point_result(result, "ATM")

        self.assertTrue(text.startswith(ATM_WEIGHT_MISMATCH_NOTICE))
        self.assertIn("TOGW: 59000 KG", text)
        self.assertNotIn("TOGW: 60000 KG", text)

    def test_adds_space_between_engine_failure_procedure_and_table_paths(self) -> None:
        result = SinglePointCalculationResult(
            status="success",
            request=SinglePointTakeoffRequest(
                aircraft_code="777F",
                airport_code="ZBAA",
                runway="18L",
                takeoff_weight_kg=190000,
                actual_temperature_c=25,
                wind_kt=0,
            ),
            full=SinglePointSectionResult(label="FULL"),
            full_table_path=Path("output/full/STASTBL"),
            atm_table_path=Path("output/atm/STASTBL"),
            engine_failure_procedure_title="*** NO EMERGENCY TURN ***",
        )

        text = format_single_point_result(result, "FULL")

        self.assertIn("*** NO EMERGENCY TURN ***\n\n\nFULL STASTBL:", text)


if __name__ == "__main__":
    unittest.main()
