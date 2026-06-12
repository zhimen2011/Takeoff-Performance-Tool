from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
sys.path.insert(0, str(SRC_DIR))

from stas_app.models.report import ReportExportResult
from stas_app.models.request import PerformanceRequest
from stas_app.models.result import StasRunResult
from stas_app.models.config import MANUAL_PDF_REPORT_FILENAME, MANUAL_WORD_REPORT_FILENAME, TEMPORARY_PDF_REPORT_FILENAME, TEMPORARY_WORD_REPORT_FILENAME
from stas_app.parsers.runway_parser import parse_runway_file
from stas_app.services.aircraft_registry import AircraftRegistry
from stas_app.services.input_builder import StasInputBuilder
from stas_app.services.performance_service import PerformanceService


class FakeStasEngine:
    def __init__(self, run_dir: Path, status: str = "success") -> None:
        self.run_dir = run_dir
        self.status = status
        self.requests: list[PerformanceRequest] = []
        self.input_contents: list[str] = []

    def run(self, request: PerformanceRequest, input_content: str) -> StasRunResult:
        self.requests.append(request)
        self.input_contents.append(input_content)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        input_path = self.run_dir / "STASINP"
        input_path.write_text(input_content, encoding="utf-8")

        if self.status != "success":
            return StasRunResult(
                status="error",
                run_dir=self.run_dir,
                input_path=input_path,
                error_message="simulated STAS failure",
            )

        output_path = self.run_dir / "STASOUT.out"
        output_path.write_text("ELEVATION 1000 FT\nRESULT", encoding="utf-8")
        return StasRunResult(
            status="success",
            run_dir=self.run_dir,
            input_path=input_path,
            raw_output_path=output_path,
        )


class FakeWordExporter:
    def __init__(self, status: str = "success") -> None:
        self.status = status
        self.calls: list[tuple[Path, Path, Path | None, str]] = []

    def export(
        self,
        stas_output_path: str | Path,
        docx_path: str | Path,
        logo_path: str | Path | None = None,
        report_date_override: str = "",
    ) -> ReportExportResult:
        source = Path(stas_output_path)
        target = Path(docx_path)
        self.calls.append((source, target, Path(logo_path) if logo_path else None, report_date_override))

        if self.status != "success":
            return ReportExportResult(status="error", output_path=target, error_message="word failed")

        target.write_text("docx", encoding="utf-8")
        return ReportExportResult(status="success", output_path=target)


class FakePDFExporter:
    def __init__(self, status: str = "success") -> None:
        self.status = status
        self.calls: list[tuple[Path, Path]] = []

    def export(self, docx_path: str | Path, pdf_path: str | Path) -> ReportExportResult:
        source = Path(docx_path)
        target = Path(pdf_path)
        self.calls.append((source, target))

        if self.status != "success":
            return ReportExportResult(status="error", output_path=target, error_message="pdf failed")

        target.write_text("pdf", encoding="utf-8")
        return ReportExportResult(status="success", output_path=target)


class FakeManualWordExporter:
    def __init__(self, status: str = "success") -> None:
        self.status = status
        self.calls: list[tuple[Path, Path, str, PerformanceRequest | None]] = []

    def export(
        self,
        stas_output_path: str | Path,
        docx_path: str | Path,
        template_id: str,
        request: PerformanceRequest | None = None,
    ) -> ReportExportResult:
        source = Path(stas_output_path)
        target = Path(docx_path)
        self.calls.append((source, target, template_id, request))

        if self.status != "success":
            return ReportExportResult(status="error", output_path=target, error_message="manual word failed")

        target.write_text("manual docx", encoding="utf-8")
        return ReportExportResult(status="success", output_path=target)


class FakeRunwayProcedureEnricher:
    def __init__(self, status: str = "success") -> None:
        self.status = status
        self.calls: list[tuple[Path, Path]] = []

    def enrich_file(self, stas_output_path: str | Path, target_path: str | Path | None = None) -> Path:
        source = Path(stas_output_path)
        target = Path(target_path) if target_path else source.with_name(f"{source.stem}.enriched{source.suffix}")
        self.calls.append((source, target))

        if self.status != "success":
            raise ValueError("enrichment failed")

        target.write_text(source.read_text(encoding="utf-8") + "\nENRICHED", encoding="utf-8")
        return target


class PerformanceServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = AircraftRegistry.from_directory(ROOT_DIR / "config" / "aircraft")
        self.runways = parse_runway_file(ROOT_DIR / "tests" / "fixtures" / "APTRWY_SAMPLE.RWY")
        self.input_builder = StasInputBuilder(ROOT_DIR / "templates", "C:/STAS/APTRWY.RWY")

    def test_calculate_runs_full_success_flow(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = Path(temp_dir) / "run"
            stas_engine = FakeStasEngine(run_dir)
            word_exporter = FakeWordExporter()
            pdf_exporter = FakePDFExporter()
            service = PerformanceService(
                aircraft_registry=self.registry,
                runway_dataset=self.runways,
                input_builder=self.input_builder,
                stas_engine=stas_engine,
                word_exporter=word_exporter,
                pdf_exporter=pdf_exporter,
            )
            request = PerformanceRequest(
                aircraft_code="738",
                airport_code="ZBAA",
                runways=("18L",),
                qnh_ref="1012",
            )

            result = service.calculate(request)

            self.assertTrue(result.succeeded, result.error_message)
            self.assertTrue(result.stas_run and result.stas_run.succeeded)
            self.assertTrue(result.word_report and result.word_report.succeeded)
            self.assertTrue(result.pdf_report and result.pdf_report.succeeded)
            self.assertIsNone(result.manual_word_report)
            self.assertIsNone(result.manual_pdf_report)
            self.assertEqual(result.warnings, ())
            self.assertIn("SELECT RUNWAY ZBAA/18L", stas_engine.input_contents[0])
            self.assertEqual(word_exporter.calls[0][1], run_dir / TEMPORARY_WORD_REPORT_FILENAME)
            self.assertEqual(pdf_exporter.calls[0][1], run_dir / TEMPORARY_PDF_REPORT_FILENAME)

    def test_validation_failure_stops_before_stas_execution(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            stas_engine = FakeStasEngine(Path(temp_dir) / "run")
            word_exporter = FakeWordExporter()
            pdf_exporter = FakePDFExporter()
            service = PerformanceService(
                aircraft_registry=self.registry,
                runway_dataset=self.runways,
                input_builder=self.input_builder,
                stas_engine=stas_engine,
                word_exporter=word_exporter,
                pdf_exporter=pdf_exporter,
            )

            result = service.calculate(PerformanceRequest(aircraft_code="733", airport_code="ZBAA"))

            self.assertFalse(result.succeeded)
            self.assertIn("Unsupported aircraft", result.error_message)
            self.assertEqual(stas_engine.requests, [])
            self.assertEqual(word_exporter.calls, [])
            self.assertEqual(pdf_exporter.calls, [])

    def test_stas_failure_stops_report_exports(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            stas_engine = FakeStasEngine(Path(temp_dir) / "run", status="error")
            word_exporter = FakeWordExporter()
            pdf_exporter = FakePDFExporter()
            service = PerformanceService(
                aircraft_registry=self.registry,
                runway_dataset=self.runways,
                input_builder=self.input_builder,
                stas_engine=stas_engine,
                word_exporter=word_exporter,
                pdf_exporter=pdf_exporter,
            )

            result = service.calculate(PerformanceRequest(aircraft_code="738", airport_code="ZBAA"))

            self.assertFalse(result.succeeded)
            self.assertIn("simulated STAS failure", result.error_message)
            self.assertEqual(word_exporter.calls, [])
            self.assertEqual(pdf_exporter.calls, [])

    def test_word_failure_is_reported_as_warning_and_skips_pdf(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            stas_engine = FakeStasEngine(Path(temp_dir) / "run")
            word_exporter = FakeWordExporter(status="error")
            pdf_exporter = FakePDFExporter()
            service = PerformanceService(
                aircraft_registry=self.registry,
                runway_dataset=self.runways,
                input_builder=self.input_builder,
                stas_engine=stas_engine,
                word_exporter=word_exporter,
                pdf_exporter=pdf_exporter,
            )

            result = service.calculate(PerformanceRequest(aircraft_code="738", airport_code="ZBAA"))

            self.assertTrue(result.succeeded)
            self.assertTrue(result.word_report)
            self.assertFalse(result.word_report.succeeded)
            self.assertIsNone(result.pdf_report)
            self.assertIn("Temporary takeoff Word report was not generated", result.warnings[0])
            self.assertEqual(pdf_exporter.calls, [])

    def test_pdf_failure_is_reported_as_warning(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            stas_engine = FakeStasEngine(Path(temp_dir) / "run")
            pdf_exporter = FakePDFExporter(status="error")
            service = PerformanceService(
                aircraft_registry=self.registry,
                runway_dataset=self.runways,
                input_builder=self.input_builder,
                stas_engine=stas_engine,
                word_exporter=FakeWordExporter(),
                pdf_exporter=pdf_exporter,
            )

            result = service.calculate(PerformanceRequest(aircraft_code="738", airport_code="ZBAA"))

            self.assertTrue(result.succeeded)
            self.assertTrue(result.pdf_report)
            self.assertFalse(result.pdf_report.succeeded)
            self.assertIn("Temporary takeoff PDF report was not generated", result.warnings[0])

    def test_report_date_override_is_passed_to_temporary_word_exporter(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = Path(temp_dir) / "run"
            stas_engine = FakeStasEngine(run_dir)
            word_exporter = FakeWordExporter()
            service = PerformanceService(
                aircraft_registry=self.registry,
                runway_dataset=self.runways,
                input_builder=self.input_builder,
                stas_engine=stas_engine,
                word_exporter=word_exporter,
                pdf_exporter=FakePDFExporter(),
            )

            result = service.calculate(
                PerformanceRequest(
                    aircraft_code="738",
                    airport_code="ZBAA",
                    runways=("18L",),
                    report_date_override="04-APR-2026",
                )
            )

            self.assertTrue(result.succeeded, result.error_message)
            self.assertEqual(word_exporter.calls[0][3], "04-APR-2026")
            self.assertTrue(result.stas_run and result.stas_run.raw_output_path)
            self.assertIn("ELEVATION 1000 FT", result.stas_run.raw_output_path.read_text(encoding="utf-8"))

    def test_manual_report_is_generated_when_template_is_selected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = Path(temp_dir) / "run"
            stas_engine = FakeStasEngine(run_dir)
            word_exporter = FakeWordExporter()
            pdf_exporter = FakePDFExporter()
            manual_word_exporter = FakeManualWordExporter()
            service = PerformanceService(
                aircraft_registry=self.registry,
                runway_dataset=self.runways,
                input_builder=self.input_builder,
                stas_engine=stas_engine,
                word_exporter=word_exporter,
                pdf_exporter=pdf_exporter,
                manual_word_exporter=manual_word_exporter,
            )

            result = service.calculate(
                PerformanceRequest(
                    aircraft_code="738",
                    airport_code="ZBAA",
                    runways=("18L",),
                    manual_report_template_id="738_normal",
                )
            )

            self.assertTrue(result.succeeded, result.error_message)
            self.assertIsNone(result.word_report)
            self.assertIsNone(result.pdf_report)
            self.assertTrue(result.manual_word_report and result.manual_word_report.succeeded)
            self.assertTrue(result.manual_pdf_report and result.manual_pdf_report.succeeded)
            self.assertEqual(word_exporter.calls, [])
            self.assertEqual(manual_word_exporter.calls[0][1], run_dir / MANUAL_WORD_REPORT_FILENAME)
            self.assertEqual(manual_word_exporter.calls[0][2], "738_normal")
            self.assertEqual(len(pdf_exporter.calls), 1)
            self.assertEqual(pdf_exporter.calls[-1][1], run_dir / MANUAL_PDF_REPORT_FILENAME)

    def test_enriched_report_output_is_used_for_word_exports(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = Path(temp_dir) / "run"
            stas_engine = FakeStasEngine(run_dir)
            word_exporter = FakeWordExporter()
            manual_word_exporter = FakeManualWordExporter()
            enricher = FakeRunwayProcedureEnricher()
            service = PerformanceService(
                aircraft_registry=self.registry,
                runway_dataset=self.runways,
                input_builder=self.input_builder,
                stas_engine=stas_engine,
                word_exporter=word_exporter,
                pdf_exporter=FakePDFExporter(),
                manual_word_exporter=manual_word_exporter,
                runway_procedure_enricher=enricher,
            )

            result = service.calculate(
                PerformanceRequest(
                    aircraft_code="738",
                    airport_code="ZBAA",
                    runways=("18L",),
                    manual_report_template_id="738_normal",
                )
            )

            self.assertTrue(result.succeeded, result.error_message)
            self.assertTrue(result.stas_run and result.stas_run.report_output_path)
            self.assertEqual(enricher.calls[0][0], run_dir / "STASOUT.out")
            self.assertEqual(word_exporter.calls, [])
            self.assertEqual(manual_word_exporter.calls[0][0], result.stas_run.report_output_path)
            self.assertIn("ENRICHED", result.stas_run.report_output_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
