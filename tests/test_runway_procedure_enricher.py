from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
sys.path.insert(0, str(SRC_DIR))

from stas_app.services.runway_procedure_enricher import (
    RunwayProcedureEnricher,
    extract_runway_display_procedures,
    extract_runway_procedures,
)


RUNWAY_FILE_CONTENT = """AIRPORT2
LTFE  BODRUM INTL         MILAS,TUR           FMLOLO       21 BJV
RWYU  90  2.50  45
'D-10L'  0  2050   2050   2050   3000   0.11  0.11  0.11 12  0
3      8  0
'*** SEE SPECIAL PROCEDURE FOR THIS RUNWAY ***                                                                        19 MAY 2026'
H At D2.5 BDR RIGHT turn to 150. At D4.5 BDR LEFT turn DCT to
H BDR (MAX 183 KTAS for all turns). Intercept OUBD R-265
H BDR.
RWYU  90  2.50  45
'28R'  0  3000   3000   3000   3000  -0.11 -0.11 -0.11 10  0
1      8  0
'NO EMERGENCY TURN'
"""


TRUNCATED_STAS_OUTPUT = """      ELEVATION    21 FT                                   RUNWAY D-10L   LTFE

      RUNWAY       HT   DIST  OFFSET     HT   DIST  OFFSET     HT   DIST  OFFSET
      D-10L         3      8       0
      ENG-OUT PROCEDURE:
      *** SEE SPECIAL PROCEDURE FOR THIS RUNWAY ***
       At D2.5 BDR RIGHT turn to 150. At D4.5 BDR LEFT turn DCT to BDR
      ELEVATION    21 FT                                   RUNWAY 28R     LTFE

      ENG-OUT PROCEDURE:
      NO EMERGENCY TURN
"""


class RunwayProcedureEnricherTests(unittest.TestCase):
    def test_extracts_h_lines_and_removes_aviation_date(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            runway_file = Path(temp_dir) / "APTRWY.RWY"
            runway_file.write_text(RUNWAY_FILE_CONTENT, encoding="utf-8")

            procedures = extract_runway_procedures(runway_file)
            display_procedures = extract_runway_display_procedures(runway_file)

            procedure = procedures[("LTFE", "D-10L")]
            self.assertEqual(procedure.title, "*** SEE SPECIAL PROCEDURE FOR THIS RUNWAY ***")
            self.assertEqual(
                procedure.detail,
                "At D2.5 BDR RIGHT turn to 150. At D4.5 BDR LEFT turn DCT to "
                "BDR (MAX 183 KTAS for all turns). Intercept OUBD R-265 BDR.",
            )
            self.assertNotIn(("LTFE", "28R"), procedures)
            self.assertEqual(display_procedures[("LTFE", "28R")].title, "*** NO EMERGENCY TURN ***")

    def test_enriches_truncated_stas_procedure_from_runtime_runway_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            runway_file = Path(temp_dir) / "APTRWY.RWY"
            runway_file.write_text(RUNWAY_FILE_CONTENT, encoding="utf-8")

            enriched = RunwayProcedureEnricher(runway_file).enrich_text(TRUNCATED_STAS_OUTPUT)

            self.assertIn("Intercept OUBD R-265 BDR.", enriched)
            self.assertNotIn("19 MAY 2026", enriched)
            self.assertIn("NO EMERGENCY TURN", enriched)
            self.assertEqual(enriched.count("*** SEE SPECIAL PROCEDURE FOR THIS RUNWAY ***"), 1)
            self.assertIn("RUNWAY 28R     LTFE", enriched)

    def test_no_emergency_turn_output_is_left_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            runway_file = Path(temp_dir) / "APTRWY.RWY"
            runway_file.write_text(
                """AIRPORT2
LTFE  BODRUM INTL         MILAS,TUR           FMLOLO       21 BJV
RWYU  90  2.50  45
'28R'  0  3000   3000   3000   3000  -0.11 -0.11 -0.11 10  0
1      8  0
'NO EMERGENCY TURN'
""",
                encoding="utf-8",
            )
            stas_output = """      ELEVATION    21 FT                                   RUNWAY 28R     LTFE

      ENG-OUT PROCEDURE:
      NO EMERGENCY TURN
"""

            enriched = RunwayProcedureEnricher(runway_file).enrich_text(stas_output)

            self.assertEqual(enriched, stas_output)


if __name__ == "__main__":
    unittest.main()
