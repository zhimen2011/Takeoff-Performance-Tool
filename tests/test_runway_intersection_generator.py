from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
sys.path.insert(0, str(SRC_DIR))

from stas_app.models.runway_database import AirportBlock
from stas_app.services.runway_intersection_generator import (
    EOSID_TEXT_SEPARATOR,
    generate_intersections_for_airport_block,
    generate_runway_intersection_blocks,
    split_intersection_names,
)


MAIN_RUNWAY_BLOCK = (
    "RWYU  90  2.50  45",
    "'10L'  0  3000   3000   3000   3000   0.11  0.11  0.11 2  0",
    "3      8  0",
    "11     58  0",
    "'*** SEE SPECIAL PROCEDURE FOR THIS RUNWAY ***                                                                        19 MAY 2026'",
    "H At D2.5 BDR RIGHT turn to 150. At D4.5 BDR LEFT turn DCT to",
    "H BDR (MAX 183 KTAS for all turns). Intercept OUBD R-265",
    "H BDR.",
    "#INT 'D' 950 90  0.11  0.11",
)


class RunwayIntersectionGeneratorTests(unittest.TestCase):
    def test_merges_multiple_h_lines_and_removes_h_prefixes(self) -> None:
        generated = generate_runway_intersection_blocks(MAIN_RUNWAY_BLOCK, "#INT 'D' 950 90  0.11  0.11", "AIRPORT2")
        merged_text_line = next(line for line in generated if line.startswith("'*** SEE SPECIAL"))

        self.assertIn(
            "At D2.5 BDR RIGHT turn to 150. At D4.5 BDR LEFT turn DCT to "
            "BDR (MAX 183 KTAS for all turns). Intercept OUBD R-265 BDR.",
            merged_text_line,
        )
        self.assertNotIn("\nH ", "\n".join(generated))

    def test_removes_trailing_aviation_date_from_text_line(self) -> None:
        generated = generate_runway_intersection_blocks(MAIN_RUNWAY_BLOCK, "#INT 'D' 950 90  0.11  0.11", "AIRPORT2")
        merged_text_line = next(line for line in generated if line.startswith("'*** SEE SPECIAL"))

        self.assertNotIn("19 MAY 2026", merged_text_line)
        self.assertIn("*** SEE SPECIAL PROCEDURE FOR THIS RUNWAY ***", merged_text_line)

    def test_requested_separator_pads_clean_base_text_before_eosid_text(self) -> None:
        generated = generate_runway_intersection_blocks(MAIN_RUNWAY_BLOCK, "#INT 'D' 950 90  0.11  0.11", "AIRPORT2")
        merged_text_line = next(line for line in generated if line.startswith("'*** SEE SPECIAL"))
        inner = merged_text_line[1:-1]
        base_text = "*** SEE SPECIAL PROCEDURE FOR THIS RUNWAY ***"
        eosid_text = (
            "At D2.5 BDR RIGHT turn to 150. At D4.5 BDR LEFT turn DCT to "
            "BDR (MAX 183 KTAS for all turns). Intercept OUBD R-265 BDR."
        )

        self.assertEqual(inner, f"{base_text}{EOSID_TEXT_SEPARATOR}{eosid_text}")

    def test_generates_intersection_runway_distances_and_lineup(self) -> None:
        generated = generate_runway_intersection_blocks(MAIN_RUNWAY_BLOCK, "#INT 'D' 950 90  0.11  0.11", "AIRPORT2")

        self.assertEqual(generated[0], "RWYU 90 2.50 45")
        self.assertIn("'D-10L'", generated[1])
        self.assertIn("2050", generated[1])
        self.assertEqual(generated[-1], "#INT 'D' 950 90  0.11  0.11")

    def test_hyphenated_intersection_name_splits_into_individual_names(self) -> None:
        self.assertEqual(split_intersection_names("H4-G6"), ("H4", "G6"))

    def test_slash_intersection_name_splits_into_individual_names(self) -> None:
        self.assertEqual(split_intersection_names("H4/G6"), ("H4", "G6"))

    def test_airport2_hyphenated_intersections_generate_separate_runways(self) -> None:
        block = AirportBlock(
            icao="RKSI",
            record_type="AIRPORT2",
            raw_lines=(
                "AIRPORT2",
                "RKSI  INCHEON INTL        SEOUL/INCHEON,KOR",
                "RWYU  90  2.50  60",
                "'15L'  0  3750   4050   3870   3750   0.00  0.00  0.00 0   2",
                "'*** NO EMERGENCY TURN ***'",
                "#INT 'D4-C8' 1200 90  0.00  0.00",
            ),
            runway_ids=("15L",),
        )

        generated = generate_intersections_for_airport_block(block)
        content = "\n".join(generated.raw_lines)

        self.assertIn("'D4-15L'", content)
        self.assertIn("'C8-15L'", content)
        self.assertNotIn("D4/C8-15L", content)
        self.assertEqual(generated.runway_ids, ("15L", "D4-15L", "C8-15L"))

    def test_intersection_runway_id_longer_than_stas_limit_raises_clear_error(self) -> None:
        block = AirportBlock(
            icao="RKSI",
            record_type="AIRPORT2",
            raw_lines=(
                "AIRPORT2",
                "RKSI  INCHEON INTL        SEOUL/INCHEON,KOR",
                "RWYU  90  2.50  60",
                "'15L'  0  3750   4050   3870   3750   0.00  0.00  0.00 0   2",
                "'*** NO EMERGENCY TURN ***'",
                "#INT 'ABCDE' 1200 90  0.00  0.00",
            ),
            runway_ids=("15L",),
        )

        with self.assertRaisesRegex(ValueError, "ABCDE-15L"):
            generate_intersections_for_airport_block(block)

    def test_existing_eight_character_intersection_runway_id_is_allowed(self) -> None:
        block = AirportBlock(
            icao="EBBR",
            record_type="AIRPORT2",
            raw_lines=(
                "AIRPORT2",
                "EBBR  BRUSSELS NATIONAL",
                "RWYU  0  2.50  45",
                "'PSN1-07R'  0  2624   2624   2624   3088   -0.17  -0.17  -0.17 3   0",
            ),
            runway_ids=("PSN1-07R",),
        )

        generated = generate_intersections_for_airport_block(block)

        self.assertEqual(generated.runway_ids, ("PSN1-07R",))

    def test_existing_compound_intersection_runway_id_splits_into_separate_records(self) -> None:
        block = AirportBlock(
            icao="OERK",
            record_type="AIRPORT2",
            raw_lines=(
                "AIRPORT2",
                "OERK  KING KHALID INTL",
                "RWYU  90  2.50  60",
                "'H4/G6-15L'  0  3542   3542   3542   4205  -0.15 -0.15 -0.15 0   0",
            ),
            runway_ids=("H4/G6-15L",),
        )

        generated = generate_intersections_for_airport_block(block)
        content = "\n".join(generated.raw_lines)

        self.assertEqual(generated.runway_ids, ("H4-15L", "G6-15L"))
        self.assertIn("'H4-15L'", content)
        self.assertIn("'G6-15L'", content)
        self.assertNotIn("'H4/G6-15L'", content)

    def test_airport_block_appends_generated_intersections_once(self) -> None:
        block = AirportBlock(
            icao="LTFE",
            record_type="AIRPORT2",
            raw_lines=(
                "AIRPORT2",
                "LTFE  BODRUM INTL         MILAS,TUR           FMLOLO       21 BJV",
                *MAIN_RUNWAY_BLOCK,
            ),
            runway_ids=("10L",),
        )

        generated_once = generate_intersections_for_airport_block(block)
        generated_twice = generate_intersections_for_airport_block(generated_once)

        self.assertEqual(generated_once.runway_ids, ("10L", "D-10L"))
        self.assertEqual(generated_twice.runway_ids, generated_once.runway_ids)
        self.assertEqual(generated_twice.raw_lines.count("RWYU 90 2.50 45"), 1)

    def test_airport_block_cleans_original_full_runway_text(self) -> None:
        block = AirportBlock(
            icao="LTFE",
            record_type="AIRPORT2",
            raw_lines=(
                "AIRPORT2",
                "LTFE  BODRUM INTL         MILAS,TUR           FMLOLO       21 BJV",
                *MAIN_RUNWAY_BLOCK,
            ),
            runway_ids=("10L",),
        )

        generated = generate_intersections_for_airport_block(block)
        content = "\n".join(generated.raw_lines)

        self.assertNotIn("19 MAY 2026", content)
        self.assertNotIn("\nH At D2.5", content)
        self.assertIn(
            f"'*** SEE SPECIAL PROCEDURE FOR THIS RUNWAY ***{EOSID_TEXT_SEPARATOR}At D2.5 BDR RIGHT",
            content,
        )


if __name__ == "__main__":
    unittest.main()
