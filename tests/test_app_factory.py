from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
sys.path.insert(0, str(SRC_DIR))

from stas_app.models.config import AppConfig
from stas_app.models.report import ReportExportResult
from stas_app.models.request import PerformanceRequest
from stas_app.services.app_factory import create_application_context, create_performance_service


FAKE_STAS = ROOT_DIR / "tests" / "fixtures" / "fake_stas.py"


class FakeWordExporter:
    def export(
        self,
        stas_output_path: str | Path,
        docx_path: str | Path,
        logo_path: str | Path | None = None,
        report_date_override: str = "",
    ) -> ReportExportResult:
        target = Path(docx_path)
        target.write_text("docx", encoding="utf-8")
        return ReportExportResult(status="success", output_path=target)


class FakePDFExporter:
    def export(self, docx_path: str | Path, pdf_path: str | Path) -> ReportExportResult:
        target = Path(pdf_path)
        target.write_text("pdf", encoding="utf-8")
        return ReportExportResult(status="success", output_path=target)


class AppFactoryTests(unittest.TestCase):
    def test_create_performance_service_runs_with_fake_stas(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            work_dir = root / "work"
            output_root = root / "output"
            work_dir.mkdir()
            airport_file = work_dir / "APTRWY.RWY"
            master_file = work_dir / "APTRWY_MASTER.RWY"
            master_file.write_text(
                (ROOT_DIR / "tests" / "fixtures" / "APTRWY_SAMPLE.RWY").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            airport_file.write_text("OLD RUNTIME FILE\n", encoding="utf-8")
            config = AppConfig(
                aircraft_config_dir=ROOT_DIR / "config" / "aircraft",
                template_dir=ROOT_DIR / "templates",
                airport_runway_file=airport_file,
                airport_runway_master_file=master_file,
                stas_executable_path=Path(sys.executable),
                stas_work_dir=work_dir,
                output_root=output_root,
                executable_args=(str(FAKE_STAS), "success"),
                timeout_seconds=10,
            )

            service = create_performance_service(
                config,
                word_exporter=FakeWordExporter(),
                pdf_exporter=FakePDFExporter(),
            )
            result = service.calculate(
                PerformanceRequest(
                    aircraft_code="738",
                    airport_code="ZBAA",
                    runways=("18L",),
                )
            )

            self.assertTrue(result.succeeded, result.error_message)
            self.assertTrue(result.stas_run and result.stas_run.raw_output_path)
            self.assertTrue(result.word_report and result.word_report.output_path and result.word_report.output_path.exists())
            self.assertTrue(result.pdf_report and result.pdf_report.output_path and result.pdf_report.output_path.exists())
            self.assertIn("AIRPORT FILE APTRWY.RWY", result.stas_run.input_path.read_text(encoding="utf-8"))
            self.assertIn("ZBAA", airport_file.read_text(encoding="utf-8"))
            self.assertIn("'A1-18L'", airport_file.read_text(encoding="utf-8"))
            self.assertNotIn("ZSPD", airport_file.read_text(encoding="utf-8"))

    def test_create_application_context_falls_back_to_runtime_file_when_master_is_not_created_yet(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            work_dir = root / "work"
            work_dir.mkdir()
            airport_file = work_dir / "APTRWY.RWY"
            master_file = work_dir / "APTRWY_MASTER.RWY"
            airport_file.write_text(
                (ROOT_DIR / "tests" / "fixtures" / "APTRWY_SAMPLE.RWY").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            config = AppConfig(
                aircraft_config_dir=ROOT_DIR / "config" / "aircraft",
                template_dir=ROOT_DIR / "templates",
                airport_runway_file=airport_file,
                airport_runway_master_file=master_file,
                stas_executable_path=Path(sys.executable),
                stas_work_dir=work_dir,
                output_root=root / "output",
                executable_args=(str(FAKE_STAS), "success"),
                timeout_seconds=10,
            )

            context = create_application_context(config, word_exporter=FakeWordExporter(), pdf_exporter=FakePDFExporter())

            self.assertEqual(context.runway_dataset.airport_codes(), ("ZBAA", "ZSPD"))
            self.assertEqual(context.runway_dataset.get_runway_ids("ZBAA"), ("18L", "36R", "A1-18L"))
            zbaa_runways = context.runway_dataset.get_airport("ZBAA").runways
            self.assertEqual(zbaa_runways[0].tora_m, 3200)
            self.assertFalse(zbaa_runways[0].is_intersection)
            self.assertEqual(zbaa_runways[2].tora_m, 3100)
            self.assertTrue(zbaa_runways[2].is_intersection)
            self.assertEqual(context.runway_import_service.master_file, master_file)


if __name__ == "__main__":
    unittest.main()
