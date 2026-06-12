from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
sys.path.insert(0, str(SRC_DIR))

from stas_app.parsers.stas_table_parser import is_stas_null, parse_stas_table_text


class StasTableParserTests(unittest.TestCase):
    def test_parses_variable_table_headers_and_rows(self) -> None:
        rows = parse_stas_table_text(
            """
 POPT(024)    CLIMIT(001)    CLIMIT(019)    CLIMIT(006)    CLIMIT(005)    ACCSEG(002)
   20000.       20000.       120.4       130.5       140.6       400.4
   60000.       60000.       150.5       151.49      152.5       415.49
"""
        )

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1]["POPT(024)"], 60000)
        self.assertEqual(rows[1]["CLIMIT(019)"], 150.5)
        self.assertEqual(rows[1]["ACCSEG(002)"], 415.49)

    def test_detects_stas_null_values(self) -> None:
        self.assertTrue(is_stas_null(0.900000e21))
        self.assertTrue(is_stas_null(None))
        self.assertFalse(is_stas_null(415.5))


if __name__ == "__main__":
    unittest.main()
