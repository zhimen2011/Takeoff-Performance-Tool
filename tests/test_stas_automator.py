from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
sys.path.insert(0, str(SRC_DIR))

from stas_app.models.request import PerformanceRequest
from stas_app.models.result import PerformanceCalculationResult, StasRunResult
from stas_app.services.stas_automator import STASAutomator, build_default_template_order


class FakePerformanceService:
    def __init__(self, output_path: Path) -> None:
        self.output_path = output_path
        self.requests: list[PerformanceRequest] = []

    def calculate(self, request: PerformanceRequest) -> PerformanceCalculationResult:
        self.requests.append(request)
        run_dir = self.output_path.parent
        return PerformanceCalculationResult(
            status="success",
            request=request,
            stas_run=StasRunResult(
                status="success",
                run_dir=run_dir,
                input_path=run_dir / "STASINP",
                raw_output_path=self.output_path,
            ),
        )


class StasAutomatorTests(unittest.TestCase):
    def test_build_default_template_order_matches_old_777f_template_sequence(self) -> None:
        queue = build_default_template_order(
            {
                "aircraft": "777F",
                "airport_runway": "ZGGG/02L",
                "anti_ice": "OFF",
                "derate": 0,
            }
        )

        self.assertEqual(
            [(task["runway_condition"], task["bleed"]) for task in queue],
            [("DRY", "ON"), ("DRY", "OFF"), ("WET", "ON"), ("WET", "OFF")],
        )
        self.assertEqual(queue[0]["scenario_id"], "job_01_DRY_BLEED_ON")
        self.assertEqual(queue[3]["scenario_id"], "job_04_WET_BLEED_OFF")

    def test_build_default_template_order_matches_old_738_template_sequence(self) -> None:
        queue = build_default_template_order(
            {
                "scenario_id": "HNL_738",
                "aircraft": "738",
                "airport_runway": "HNL/08L",
                "anti_ice": "OFF",
            }
        )

        self.assertEqual(
            [(task["runway_condition"], task["bleed"]) for task in queue],
            [("DRY", "AUTO"), ("DRY", "OFF"), ("WET", "AUTO"), ("WET", "OFF")],
        )
        self.assertEqual(queue[0]["scenario_id"], "HNL_738_01_DRY_BLEED_AUTO")

    def test_runs_task_queue_and_merges_task_with_parsed_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "STASOUT.out"
            output_path.write_text(
                """
      ELEVATION    13 FT                                   RUNWAY 08L     HNL
      *** FLAPS 05 ***   AIR COND OFF    ANTI-ICE OFF        HONOLULU
      OAT  CLIMB         WIND COMPONENT IN KNOTS (MINUS DENOTES TAILWIND)
       F   100LB         0
      -20   1900  1900F/44-46-54
""",
                encoding="utf-8",
            )
            service = FakePerformanceService(output_path)
            automator = STASAutomator(service)

            frame = automator.run_task_queue(
                [
                    {
                        "aircraft": "738",
                        "airport_runway": "HNL/08L",
                        "runway_condition": "DRY",
                        "bleed": "OFF",
                        "anti_ice": "OFF",
                    }
                ]
            )

        self.assertEqual(len(service.requests), 1)
        self.assertEqual(service.requests[0].aircraft_code, "738")
        self.assertEqual(service.requests[0].airport_code, "HNL")
        self.assertEqual(service.requests[0].runways, ("08L",))
        self.assertEqual(frame.loc[0, "task_bleed"], "OFF")
        self.assertEqual(frame.loc[0, "mtow"], 190000)
        self.assertEqual(frame.loc[0, "v1"], 44)


if __name__ == "__main__":
    unittest.main()
