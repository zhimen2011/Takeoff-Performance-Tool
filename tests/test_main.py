from __future__ import annotations

import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
sys.path.insert(0, str(SRC_DIR))

from stas_app.main import main
from stas_app.models.report import ReportExportResult
from stas_app.models.request import PerformanceRequest
from stas_app.models.result import PerformanceCalculationResult, StasRunResult
from stas_app.storage.config_repository import ConfigError


class FakeService:
    def __init__(self) -> None:
        self.request: PerformanceRequest | None = None

    def calculate(self, request: PerformanceRequest) -> PerformanceCalculationResult:
        self.request = request
        run_dir = Path("output/run")
        stas_run = StasRunResult(
            status="success",
            run_dir=run_dir,
            input_path=run_dir / "STASINP",
            raw_output_path=run_dir / "STASOUT.out",
        )
        return PerformanceCalculationResult(
            status="success",
            request=request,
            stas_run=stas_run,
        )


class FakeServiceWithFailedPDF(FakeService):
    def calculate(self, request: PerformanceRequest) -> PerformanceCalculationResult:
        result = super().calculate(request)
        return PerformanceCalculationResult(
            status="success",
            request=result.request,
            stas_run=result.stas_run,
            pdf_report=ReportExportResult(
                status="error",
                output_path=Path("output/run/STASOUT.pdf"),
                error_message="pdf failed",
            ),
            warnings=("PDF report was not generated: pdf failed",),
        )


class MainTests(unittest.TestCase):
    def test_calculate_command_builds_request_and_prints_success(self) -> None:
        fake_service = FakeService()
        stdout = io.StringIO()

        with patch("stas_app.main.load_app_config", return_value=object()):
            with patch("stas_app.main.create_performance_service", return_value=fake_service):
                with contextlib.redirect_stdout(stdout):
                    code = main(
                        [
                            "calculate",
                            "--config",
                            "config/app.local.toml",
                            "--aircraft",
                            "777F",
                            "--airport",
                            "ZBAA",
                            "--runway",
                            "18L",
                            "--runway",
                            "36R",
                            "--qnh",
                            "1013.25",
                            "--thrust-option",
                            "1L1BUMP",
                            "--report-date",
                            "04-APR-2026",
                        ]
                    )

        self.assertEqual(code, 0)
        self.assertIn("计算完成", stdout.getvalue())
        self.assertIsNotNone(fake_service.request)
        self.assertEqual(fake_service.request.aircraft_code, "777F")
        self.assertEqual(fake_service.request.airport_code, "ZBAA")
        self.assertEqual(fake_service.request.runways, ("18L", "36R"))
        self.assertEqual(fake_service.request.qnh_ref, "1013.25")
        self.assertEqual(fake_service.request.thrust_option, "1L1BUMP")
        self.assertEqual(fake_service.request.report_date_override, "04-APR-2026")

    def test_config_error_returns_startup_failure_code(self) -> None:
        stderr = io.StringIO()

        with patch("stas_app.main.load_app_config", side_effect=ConfigError("bad config")):
            with contextlib.redirect_stderr(stderr):
                code = main(
                    [
                        "calculate",
                        "--aircraft",
                        "738",
                        "--airport",
                        "ZBAA",
                    ]
                )

        self.assertEqual(code, 2)
        self.assertIn("配置或启动失败", stderr.getvalue())

    def test_failed_pdf_does_not_print_pdf_report_path(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()

        with patch("stas_app.main.load_app_config", return_value=object()):
            with patch("stas_app.main.create_performance_service", return_value=FakeServiceWithFailedPDF()):
                with contextlib.redirect_stdout(stdout):
                    with contextlib.redirect_stderr(stderr):
                        code = main(
                            [
                                "calculate",
                                "--aircraft",
                                "738",
                                "--airport",
                                "EGNX",
                            ]
                        )

        self.assertEqual(code, 0)
        self.assertNotIn("PDF 报告", stdout.getvalue())
        self.assertIn("PDF report was not generated", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
