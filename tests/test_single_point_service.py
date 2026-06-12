from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
sys.path.insert(0, str(SRC_DIR))

from stas_app.models.request import PerformanceRequest
from stas_app.models.result import StasRunResult
from stas_app.models.runway import AirportRunways, Runway, RunwayDataset
from stas_app.models.single_point import SinglePointTakeoffRequest
from stas_app.services.aircraft_registry import AircraftRegistry
from stas_app.services.single_point_input_builder import SinglePointInputBuilder
from stas_app.services.single_point_service import ATM_WEIGHT_MISMATCH_NOTICE, SinglePointTakeoffService


FULL_TABLE = """
 POPT(024)    CLIMIT(001)    CLIMIT(019)    CLIMIT(006)    CLIMIT(005)    SPOUTA(005)    CLIMIT(028)    SPOUTA(032)    ACCSEG(002)    CLIMIT(022)    CLIMIT(023)    CLIMIT(024)    CLIMIT(026)
   20000.       20000.       100.1       101.1       102.1       120.1       90.1000       0.0000       300.100       1000.       1100.       1200.       900.
   60000.       60000.       150.5       151.49      152.5       160.5       101.853      0.0000       415.49       3000.       3200.       3300.5      1600.5
"""

ATM_TABLE = """
 POPT(024)    CLIMIT(001)    CLIMIT(044)    CLIMIT(019)    CLIMIT(006)    CLIMIT(005)    SPOUTA(005)    CLIMIT(028)    SPOUTA(032)    ACCSEG(002)    CLIMIT(022)    CLIMIT(023)    CLIMIT(024)    CLIMIT(026)
   20000.       20000.       40.0       100.1       101.1       102.1       120.1       80.1000       10.0000       300.100       1000.       1100.       1200.       900.
   60000.       60000.       47.4       151.49      152.5       153.5       161.49      91.9438      20.7097      415.5        3100.       3300.       3400.       1650.5
"""

FULL_LIMIT_REDUCED_TABLE = """
 POPT(024)    CLIMIT(001)    CLIMIT(019)    CLIMIT(006)    CLIMIT(005)    SPOUTA(005)    CLIMIT(028)    SPOUTA(032)    ACCSEG(002)    CLIMIT(022)    CLIMIT(023)    CLIMIT(024)    CLIMIT(026)
   60000.       59000.       150.5       151.49      152.5       160.5       101.853      0.0000       415.49       3000.       3200.       3300.5      1600.5
"""

ATM_LIMIT_REDUCED_TABLE = """
 POPT(024)    CLIMIT(001)    CLIMIT(044)    CLIMIT(019)    CLIMIT(006)    CLIMIT(005)    SPOUTA(005)    CLIMIT(028)    SPOUTA(032)    ACCSEG(002)    CLIMIT(022)    CLIMIT(023)    CLIMIT(024)    CLIMIT(026)
   60000.       59000.       47.4       151.49      152.5       153.5       161.49      91.9438      20.7097      415.5        3100.       3300.       3400.       1650.5
"""

RUNWAY_FILE = """AIRPORT2
ZBAA  BEIJING CAPITAL      BEIJING,CHN         FMLOLO       116 PEK
RWYU  90  2.50  45
'18L'  0  3000   3000   3000   3000   0.00  0.00  0.00 10  0
1      8  0
'*** SEE SPECIAL PROCEDURE FOR THIS RUNWAY ***'
H Turn right to heading 210.
RWYU  90  2.50  45
'36R'  0  3000   3000   3000   3000   0.00  0.00  0.00 10  0
1      8  0
'NO EMERGENCY TURN'
"""


class FakeTableStasEngine:
    def __init__(
        self,
        work_dir: Path,
        output_root: Path,
        tables: tuple[str, ...],
        statuses: tuple[str, ...] | None = None,
    ) -> None:
        self.work_dir = work_dir
        self.output_root = output_root
        self.tables = tables
        self.statuses = statuses or tuple("success" for _ in tables)
        self.calls: list[tuple[PerformanceRequest, str]] = []

    def run(self, request: PerformanceRequest, input_content: str) -> StasRunResult:
        self.calls.append((request, input_content))
        run_dir = self.output_root / request.scenario_id
        run_dir.mkdir(parents=True, exist_ok=True)
        input_path = run_dir / "STASINP"
        output_path = run_dir / "STASOUT.out"
        input_path.write_text(input_content, encoding="utf-8")
        output_path.write_text("STASOUT", encoding="utf-8")
        index = len(self.calls) - 1
        table = self.tables[index]
        (self.work_dir / "STASTBL").write_text(table, encoding="utf-8")
        status = self.statuses[index]
        return StasRunResult(
            status=status,
            run_dir=run_dir,
            input_path=input_path,
            raw_output_path=output_path,
            return_code=0 if status == "success" else 1,
            stas_error="" if status == "success" else "Invalid Maximum computational weight value input.",
            error_message="" if status == "success" else "STAS exited with return code 1",
        )


class SinglePointTakeoffServiceTests(unittest.TestCase):
    def test_calculates_full_and_atm_results_from_target_weight_row(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            work_dir = root / "work"
            output_root = root / "output"
            runway_file = root / "APTRWY.RWY"
            work_dir.mkdir()
            runway_file.write_text(RUNWAY_FILE, encoding="utf-8")
            registry = AircraftRegistry.from_directory(ROOT_DIR / "config" / "aircraft")
            service = SinglePointTakeoffService(
                aircraft_registry=registry,
                runway_dataset=RunwayDataset.from_airports(
                    [
                        AirportRunways(
                            "ZBAA",
                            (
                                Runway(
                                    "18L",
                                    "RWYU",
                                    tora_m=3000,
                                    toda_m=3260,
                                    asda_m=3000,
                                    slope_percent=0.25,
                                ),
                            ),
                        )
                    ]
                ),
                input_builder=SinglePointInputBuilder(ROOT_DIR / "templates", "APTRWY.RWY"),
                stas_engine=FakeTableStasEngine(work_dir, output_root, (FULL_TABLE, ATM_TABLE)),
                stas_work_dir=work_dir,
                runway_procedure_file=runway_file,
            )

            result = service.calculate(
                SinglePointTakeoffRequest(
                    aircraft_code="738",
                    airport_code="ZBAA",
                    runway="18L",
                    takeoff_weight_kg=60000,
                    actual_temperature_c=25,
                    wind_kt=0,
                    qnh_ref=1013.25,
                )
            )

            self.assertTrue(result.succeeded, result.error_message)
            self.assertEqual(result.request.flap_setting, "5")
            self.assertIsNotNone(result.full)
            self.assertIsNotNone(result.atm)
            self.assertEqual((result.full.v1, result.full.vr, result.full.v2), (151, 151, 153))
            self.assertEqual(result.full.vref30, 161)
            self.assertEqual(result.full.takeoff_thrust, 101.9)
            self.assertEqual(result.full.accel_height_ft, 415)
            self.assertEqual(result.full.ae_go_m, 1631)
            self.assertEqual(result.full.eo_go_m, 3230)
            self.assertEqual(result.full.accel_stop_m, 3346)
            self.assertEqual(result.full.tora_m, 3000)
            self.assertEqual(result.full.toda_m, 3260)
            self.assertEqual(result.full.asda_m, 3000)
            self.assertEqual(result.full.slope_percent, 0.25)
            self.assertEqual(result.atm.temperature_c, 47.4)
            self.assertEqual((result.atm.v1, result.atm.vr, result.atm.v2), (151, 153, 154))
            self.assertEqual(result.atm.reduction_percent, 20.7)
            self.assertEqual(result.atm.accel_height_ft, 416)
            self.assertEqual(result.atm.ae_go_m, 1681)
            self.assertEqual(result.atm.eo_go_m, 3330)
            self.assertEqual(result.atm.accel_stop_m, 3445)
            self.assertTrue(result.full_table_path and result.full_table_path.exists())
            self.assertTrue(result.atm_table_path and result.atm_table_path.exists())
            self.assertEqual(result.engine_failure_procedure_title, "*** SEE SPECIAL PROCEDURE FOR THIS RUNWAY ***")
            self.assertEqual(result.engine_failure_procedure_detail, "Turn right to heading 210.")

    def test_uses_target_row_when_stas_error_still_generates_table(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            work_dir = root / "work"
            output_root = root / "output"
            work_dir.mkdir()
            registry = AircraftRegistry.from_directory(ROOT_DIR / "config" / "aircraft")
            service = SinglePointTakeoffService(
                aircraft_registry=registry,
                runway_dataset=RunwayDataset.from_airports(
                    [AirportRunways("ZBAA", (Runway("18L", "RWYU"),))]
                ),
                input_builder=SinglePointInputBuilder(ROOT_DIR / "templates", "APTRWY.RWY"),
                stas_engine=FakeTableStasEngine(
                    work_dir,
                    output_root,
                    (FULL_TABLE, ATM_TABLE),
                    statuses=("error", "success"),
                ),
                stas_work_dir=work_dir,
            )

            result = service.calculate(
                SinglePointTakeoffRequest(
                    aircraft_code="738",
                    airport_code="ZBAA",
                    runway="18L",
                    takeoff_weight_kg=60000,
                    actual_temperature_c=25,
                    wind_kt=0,
                    qnh_ref=1013.25,
                )
            )

            self.assertTrue(result.succeeded, result.error_message)
            self.assertIsNotNone(result.full)
            self.assertEqual(result.full.v1, 151)
            self.assertTrue(result.warnings)
            self.assertIn("FULL STAS warning", result.warnings[0])

    def test_rejects_full_result_when_climit_weight_differs_from_requested_weight(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            work_dir = root / "work"
            output_root = root / "output"
            work_dir.mkdir()
            registry = AircraftRegistry.from_directory(ROOT_DIR / "config" / "aircraft")
            service = SinglePointTakeoffService(
                aircraft_registry=registry,
                runway_dataset=RunwayDataset.from_airports(
                    [AirportRunways("ZBAA", (Runway("18L", "RWYU"),))]
                ),
                input_builder=SinglePointInputBuilder(ROOT_DIR / "templates", "APTRWY.RWY"),
                stas_engine=FakeTableStasEngine(work_dir, output_root, (FULL_LIMIT_REDUCED_TABLE, ATM_TABLE)),
                stas_work_dir=work_dir,
            )

            result = service.calculate(
                SinglePointTakeoffRequest(
                    aircraft_code="738",
                    airport_code="ZBAA",
                    runway="18L",
                    takeoff_weight_kg=60000,
                    actual_temperature_c=25,
                    wind_kt=0,
                    qnh_ref=1013.25,
                )
            )

            self.assertFalse(result.succeeded)
            self.assertIn("FULL 计算出错", result.error_message)
            self.assertIn("59000", result.error_message)
            self.assertIn("60000", result.error_message)

    def test_atm_result_uses_climit_weight_and_notice_when_weight_differs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            work_dir = root / "work"
            output_root = root / "output"
            work_dir.mkdir()
            registry = AircraftRegistry.from_directory(ROOT_DIR / "config" / "aircraft")
            service = SinglePointTakeoffService(
                aircraft_registry=registry,
                runway_dataset=RunwayDataset.from_airports(
                    [AirportRunways("ZBAA", (Runway("18L", "RWYU"),))]
                ),
                input_builder=SinglePointInputBuilder(ROOT_DIR / "templates", "APTRWY.RWY"),
                stas_engine=FakeTableStasEngine(work_dir, output_root, (FULL_TABLE, ATM_LIMIT_REDUCED_TABLE)),
                stas_work_dir=work_dir,
            )

            result = service.calculate(
                SinglePointTakeoffRequest(
                    aircraft_code="738",
                    airport_code="ZBAA",
                    runway="18L",
                    takeoff_weight_kg=60000,
                    actual_temperature_c=25,
                    wind_kt=0,
                    qnh_ref=1013.25,
                )
            )

            self.assertTrue(result.succeeded, result.error_message)
            self.assertIsNotNone(result.atm)
            self.assertEqual(result.atm.takeoff_weight_kg, 59000)
            self.assertEqual(result.atm.notice, ATM_WEIGHT_MISMATCH_NOTICE)
            self.assertEqual((result.atm.v1, result.atm.vr, result.atm.v2), (151, 153, 154))

    def test_rejects_flap_setting_not_supported_by_aircraft(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            work_dir = root / "work"
            output_root = root / "output"
            work_dir.mkdir()
            registry = AircraftRegistry.from_directory(ROOT_DIR / "config" / "aircraft")
            service = SinglePointTakeoffService(
                aircraft_registry=registry,
                runway_dataset=RunwayDataset.from_airports(
                    [AirportRunways("ZBAA", (Runway("18L", "RWYU"),))]
                ),
                input_builder=SinglePointInputBuilder(ROOT_DIR / "templates", "APTRWY.RWY"),
                stas_engine=FakeTableStasEngine(work_dir, output_root, (FULL_TABLE, ATM_TABLE)),
                stas_work_dir=work_dir,
            )

            result = service.calculate(
                SinglePointTakeoffRequest(
                    aircraft_code="777F",
                    airport_code="ZBAA",
                    runway="18L",
                    takeoff_weight_kg=60000,
                    actual_temperature_c=25,
                    wind_kt=0,
                    qnh_ref=1013.25,
                    flap_setting="25",
                )
            )

            self.assertFalse(result.succeeded)
            self.assertIn("Unsupported flap setting", result.error_message)


if __name__ == "__main__":
    unittest.main()
