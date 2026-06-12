from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
sys.path.insert(0, str(SRC_DIR))

from stas_app.parsers.runway_parser import parse_runway_file


FIXTURE_PATH = ROOT_DIR / "tests" / "fixtures" / "APTRWY_SAMPLE.RWY"


class RunwayParserTests(unittest.TestCase):
    def test_parses_airport2_runways(self) -> None:
        dataset = parse_runway_file(FIXTURE_PATH)

        self.assertTrue(dataset.airport_exists("ZBAA"))
        self.assertEqual(dataset.get_runway_ids("ZBAA"), ("18L", "36R"))
        runways = dataset.get_airport("ZBAA").runways
        self.assertEqual(runways[0].tora_m, 3200)
        self.assertEqual(runways[0].toda_m, 3260)
        self.assertEqual(runways[0].asda_m, 3200)
        self.assertEqual(runways[0].slope_percent, 0.0)
        self.assertFalse(runways[0].is_intersection)

    def test_parses_airport1_runways_with_extra_rows(self) -> None:
        dataset = parse_runway_file(FIXTURE_PATH)

        self.assertTrue(dataset.airport_exists("ZSPD"))
        self.assertEqual(dataset.get_runway_ids("ZSPD"), ("17L",))
        self.assertEqual(dataset.get_airport("ZSPD").runways[0].tora_m, 3400)
        self.assertEqual(dataset.get_airport("ZSPD").runways[0].toda_m, 3460)
        self.assertEqual(dataset.get_airport("ZSPD").runways[0].asda_m, 3400)

    def test_airport_codes_are_sorted(self) -> None:
        dataset = parse_runway_file(FIXTURE_PATH)

        self.assertEqual(dataset.airport_codes(), ("ZBAA", "ZSPD"))

    def test_missing_file_raises_clear_error(self) -> None:
        missing_path = ROOT_DIR / "tests" / "fixtures" / "MISSING.RWY"

        with self.assertRaises(FileNotFoundError):
            parse_runway_file(missing_path)


if __name__ == "__main__":
    unittest.main()
