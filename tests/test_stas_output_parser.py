from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
sys.path.insert(0, str(SRC_DIR))

from stas_app.parsers.stas_output_parser import parse_stas_output_text


class StasOutputParserTests(unittest.TestCase):
    def test_parses_takeoff_table_cells(self) -> None:
        rows = parse_stas_output_text(
            """
      ELEVATION    13 FT                                   RUNWAY 08L     HNL

      *** FLAPS 05 ***   AIR COND OFF    ANTI-ICE OFF        HONOLULU
      OAT  CLIMB         WIND COMPONENT IN KNOTS (MINUS DENOTES TAILWIND)
       F   100LB         0              40
      -20   1900  1900F/44-46-54  1900F/46-46-54
      100   1814  1815*/44-47-53  1880*/46-47-53

      MAX BRAKE RELEASE WT MUST NOT EXCEED MAX CERT TAKEOFF WT OF     160000 LB
"""
        )

        self.assertEqual(len(rows), 4)
        self.assertEqual(rows[0]["airport_code"], "HNL")
        self.assertEqual(rows[0]["runway"], "08L")
        self.assertEqual(rows[0]["temperature"], -20)
        self.assertEqual(rows[0]["wind"], 0)
        self.assertEqual(rows[0]["mtow"], 190000)
        self.assertEqual(rows[0]["weight_unit"], "LB")
        self.assertEqual(rows[0]["limit_code"], "F")
        self.assertEqual((rows[0]["v1"], rows[0]["vr"], rows[0]["v2"]), (44, 46, 54))
        self.assertEqual(rows[3]["wind"], 40)
        self.assertEqual(rows[3]["limit_code"], "*")


if __name__ == "__main__":
    unittest.main()
