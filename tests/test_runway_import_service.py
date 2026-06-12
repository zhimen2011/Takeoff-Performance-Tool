from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
sys.path.insert(0, str(SRC_DIR))

from stas_app.models.runway_import import RUNWAY_IMPORT_OVERWRITE_EXISTING, RUNWAY_IMPORT_SKIP_EXISTING
from stas_app.parsers.runway_database_parser import parse_runway_master_file
from stas_app.services.runway_import_service import RunwayImportService


FIXTURE_PATH = ROOT_DIR / "tests" / "fixtures" / "APTRWY_SAMPLE.RWY"

MASTER_ZBAA = """# master
AIRPORT2
ZBAA  OLD AIRPORT         BEIJING,CHN
RWYS  90  2.50  45
'18L'  0  3200   3260   3200   3000   0.00  0.00  0.00 0  0
"""

SOURCE_ZBAA_ZSPD = """# source
AIRPORT2
ZBAA  NEW AIRPORT         BEIJING,CHN
RWYS  90  2.50  45
'01'  0  3200   3260   3200   3000   0.00  0.00  0.00 0  0

AIRPORT1
'ZSPD' 'PUDONG' 'SHANGHAI,CHN'
RWYV  90  2.50  45
'17L'  0  3400   3460   3400   3100   0.00  0.00  0.00 0  0
'SPECIAL ENG OUT PROCEDURE'
123 456 789
"""

SOURCE_ZSPD = """# source
AIRPORT1
'ZSPD' 'PUDONG' 'SHANGHAI,CHN'
RWYV  90  2.50  45
'17L'  0  3400   3460   3400   3100   0.00  0.00  0.00 0  0
'SPECIAL ENG OUT PROCEDURE'
123 456 789
"""


class RunwayImportServiceTests(unittest.TestCase):
    def test_skip_existing_import_adds_only_new_airports_and_backs_up_master(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            master_file = root / "APTRWY_MASTER.RWY"
            source_file = root / "IMPORT.RWY"
            master_file.write_text(MASTER_ZBAA, encoding="utf-8")
            source_file.write_text(SOURCE_ZBAA_ZSPD, encoding="utf-8")

            service = RunwayImportService(master_file)
            preview = service.preview_import(source_file, RUNWAY_IMPORT_SKIP_EXISTING)

            self.assertEqual(preview.add_count, 1)
            self.assertEqual(preview.overwrite_count, 0)
            self.assertEqual(preview.skip_count, 1)

            result = service.import_airports(source_file, RUNWAY_IMPORT_SKIP_EXISTING)
            content = master_file.read_text(encoding="utf-8")

            self.assertTrue(result.written)
            self.assertTrue(result.backup_path and result.backup_path.exists())
            self.assertIn("OLD AIRPORT", content)
            self.assertNotIn("NEW AIRPORT", content)
            self.assertIn("'ZSPD'", content)
            self.assertEqual(parse_runway_master_file(master_file).airport_codes(), ("ZBAA", "ZSPD"))

    def test_overwrite_existing_import_replaces_existing_airport_block(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            master_file = root / "APTRWY_MASTER.RWY"
            source_file = root / "IMPORT.rwy"
            master_file.write_text(MASTER_ZBAA, encoding="utf-8")
            source_file.write_text(SOURCE_ZBAA_ZSPD, encoding="utf-8")

            result = RunwayImportService(master_file).import_airports(source_file, RUNWAY_IMPORT_OVERWRITE_EXISTING)
            content = master_file.read_text(encoding="utf-8")

            self.assertTrue(result.written)
            self.assertIn("NEW AIRPORT", content)
            self.assertNotIn("OLD AIRPORT", content)
            self.assertIn("'01'", content)
            self.assertIn("'ZSPD'", content)

    def test_import_can_seed_new_master_from_runtime_airport_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            runtime_file = root / "APTRWY.RWY"
            master_file = root / "APTRWY_MASTER.RWY"
            source_file = root / "IMPORT.stx"
            runtime_file.write_text(MASTER_ZBAA, encoding="utf-8")
            source_file.write_text(SOURCE_ZSPD, encoding="utf-8")

            result = RunwayImportService(master_file, seed_file=runtime_file).import_airports(source_file)

            self.assertTrue(result.written)
            self.assertIsNone(result.backup_path)
            self.assertTrue(master_file.exists())
            self.assertEqual(parse_runway_master_file(master_file).airport_codes(), ("ZBAA", "ZSPD"))

    def test_stx_import_preview_uses_generated_airport2_intersection_runways(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            master_file = root / "APTRWY_MASTER.RWY"
            source_file = root / "IMPORT.stx"
            source_file.write_text(FIXTURE_PATH.read_text(encoding="utf-8"), encoding="utf-8")

            preview = RunwayImportService(master_file).preview_import(source_file)

            self.assertEqual(preview.source_file.suffix, ".stx")
            self.assertEqual(preview.airports[0].icao, "ZBAA")
            self.assertEqual(preview.airports[0].runway_ids, ("18L", "36R", "A1-18L"))


if __name__ == "__main__":
    unittest.main()
