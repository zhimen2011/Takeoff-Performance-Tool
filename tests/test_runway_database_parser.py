from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
sys.path.insert(0, str(SRC_DIR))

from stas_app.parsers.runway_database_parser import parse_runway_master_file
from stas_app.parsers.runway_parser import parse_runway_file
from stas_app.services.runway_runtime_file import RunwayRuntimeFileService


FIXTURE_PATH = ROOT_DIR / "tests" / "fixtures" / "APTRWY_SAMPLE.RWY"


class RunwayDatabaseParserTests(unittest.TestCase):
    def test_parses_complete_airport_blocks_from_master_file(self) -> None:
        database = parse_runway_master_file(FIXTURE_PATH)

        self.assertEqual(database.airport_codes(), ("ZBAA", "ZSPD"))
        self.assertEqual(database.profile.airport_record_types, ("AIRPORT2", "AIRPORT1"))
        self.assertEqual(database.airports["ZBAA"].record_type, "AIRPORT2")
        self.assertIn("AIRPORT2", database.airports["ZBAA"].raw_text)
        self.assertIn("'18L'", database.airports["ZBAA"].raw_text)
        self.assertIn("'36R'", database.airports["ZBAA"].raw_text)
        self.assertEqual(database.airports["ZBAA"].runway_ids, ("18L", "36R"))
        self.assertEqual(database.airports["ZSPD"].runway_ids, ("17L",))

    def test_runtime_file_service_writes_selected_complete_airport_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            master_file = root / "APTRWY_MASTER.RWY"
            runtime_file = root / "APTRWY.RWY"
            master_file.write_text(FIXTURE_PATH.read_text(encoding="utf-8"), encoding="utf-8")
            runtime_file.write_text("OLD RUNTIME FILE\n", encoding="utf-8")

            service = RunwayRuntimeFileService(master_file, runtime_file)
            service.prepare_for_airports(("ZSPD",))

            content = runtime_file.read_text(encoding="utf-8")
            self.assertIn("AIRPORT1", content)
            self.assertIn("'ZSPD'", content)
            self.assertIn("'17L'", content)
            self.assertNotIn("ZBAA", content)
            self.assertEqual(parse_runway_file(runtime_file).airport_codes(), ("ZSPD",))
            self.assertTrue(any(path.read_text(encoding="utf-8") == "OLD RUNTIME FILE\n" for path in (root / "backups").glob("*.RWY")))

    def test_runtime_file_service_generates_airport2_intersection_runways(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            master_file = root / "APTRWY_MASTER.RWY"
            runtime_file = root / "APTRWY.RWY"
            master_file.write_text(FIXTURE_PATH.read_text(encoding="utf-8"), encoding="utf-8")

            service = RunwayRuntimeFileService(master_file, runtime_file)
            service.prepare_for_airports(("ZBAA",))

            content = runtime_file.read_text(encoding="utf-8")
            self.assertIn("'A1-18L'", content)
            self.assertIn("3100", content)
            self.assertIn("Straight on extended RWY centerline.", content)
            self.assertEqual(parse_runway_file(runtime_file).get_runway_ids("ZBAA"), ("18L", "36R", "A1-18L"))

    def test_runtime_file_service_rejects_missing_airport(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            master_file = root / "APTRWY_MASTER.RWY"
            runtime_file = root / "APTRWY.RWY"
            master_file.write_text(FIXTURE_PATH.read_text(encoding="utf-8"), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "ZBAD"):
                RunwayRuntimeFileService(master_file, runtime_file).prepare_for_airports(("ZBAD",))


if __name__ == "__main__":
    unittest.main()
