from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
sys.path.insert(0, str(SRC_DIR))

from stas_app.models.request import PerformanceRequest
from stas_app.parsers.runway_parser import parse_runway_file
from stas_app.services.aircraft_registry import AircraftRegistry
from stas_app.services.validation import ValidationError, validate_performance_request


class ValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = AircraftRegistry.from_directory(ROOT_DIR / "config" / "aircraft")
        self.runways = parse_runway_file(ROOT_DIR / "tests" / "fixtures" / "APTRWY_SAMPLE.RWY")

    def test_accepts_valid_request(self) -> None:
        request = PerformanceRequest(
            aircraft_code="738",
            airport_code="ZBAA",
            runways=("18L",),
            temperature_range="65:45:5,40,25:-5:5",
            wind_range="-10,0,10,20",
            qnh_ref="1013.25",
        )

        self.assertIs(validate_performance_request(request, self.registry, self.runways), request)

    def test_rejects_removed_733_aircraft(self) -> None:
        request = PerformanceRequest(aircraft_code="733", airport_code="ZBAA")

        with self.assertRaisesRegex(ValidationError, "Unsupported aircraft"):
            validate_performance_request(request, self.registry, self.runways)

    def test_rejects_unknown_airport(self) -> None:
        request = PerformanceRequest(aircraft_code="738", airport_code="ZZZZ")

        with self.assertRaisesRegex(ValidationError, "Airport does not exist"):
            validate_performance_request(request, self.registry, self.runways)

    def test_rejects_runway_not_belonging_to_airport(self) -> None:
        request = PerformanceRequest(aircraft_code="738", airport_code="ZBAA", runways=("17L",))

        with self.assertRaisesRegex(ValidationError, "does not belong"):
            validate_performance_request(request, self.registry, self.runways)

    def test_rejects_invalid_temperature_range(self) -> None:
        request = PerformanceRequest(aircraft_code="738", airport_code="ZBAA", temperature_range="65:bad:5")

        with self.assertRaisesRegex(ValidationError, "temperature"):
            validate_performance_request(request, self.registry, self.runways)

    def test_rejects_invalid_wind_range(self) -> None:
        request = PerformanceRequest(aircraft_code="738", airport_code="ZBAA", wind_range="-10,,20")

        with self.assertRaisesRegex(ValidationError, "Wind range"):
            validate_performance_request(request, self.registry, self.runways)

    def test_rejects_invalid_qnh(self) -> None:
        request = PerformanceRequest(aircraft_code="738", airport_code="ZBAA", qnh_ref="standard")

        with self.assertRaisesRegex(ValidationError, "QNH"):
            validate_performance_request(request, self.registry, self.runways)

    def test_rejects_invalid_report_date_override(self) -> None:
        request = PerformanceRequest(aircraft_code="738", airport_code="ZBAA", report_date_override="31-APR-2026")

        with self.assertRaisesRegex(ValidationError, "Invalid report date"):
            validate_performance_request(request, self.registry, self.runways)


if __name__ == "__main__":
    unittest.main()
