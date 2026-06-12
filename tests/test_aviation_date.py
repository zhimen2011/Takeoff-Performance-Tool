from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
sys.path.insert(0, str(SRC_DIR))

from stas_app.utils.aviation_date import format_aviation_date, replace_report_date, validate_aviation_date


class AviationDateTests(unittest.TestCase):
    def test_format_aviation_date_uses_month_abbreviation(self) -> None:
        self.assertEqual(format_aviation_date(19, "may", 2026), "19-MAY-2026")
        self.assertEqual(format_aviation_date("4", 11, "2026"), "04-NOV-2026")

    def test_validate_aviation_date_rejects_invalid_day(self) -> None:
        with self.assertRaises(ValueError):
            validate_aviation_date("31-APR-2026")

    def test_replace_report_date_updates_dated_tokens_only(self) -> None:
        content = "ELEVATION\n      738 CFM DATED 19-MAY-2026\nNOT A DATE 19-MAY-2026"

        updated = replace_report_date(content, "04-APR-2026")

        self.assertIn("DATED 04-APR-2026", updated)
        self.assertIn("NOT A DATE 19-MAY-2026", updated)


if __name__ == "__main__":
    unittest.main()
