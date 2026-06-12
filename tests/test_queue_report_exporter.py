from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
sys.path.insert(0, str(SRC_DIR))

from stas_app.exporters.queue_report import QueueReportExporter
from stas_app.models.report import QueueReportResult, ReportExportResult
from stas_app.models.request import PerformanceRequest
from stas_app.models.result import PerformanceCalculationResult, StasRunResult
from stas_app.ui.forms import format_queue_report_summary


class FakeQueueWordExporter:
    def __init__(self, status: str = "success") -> None:
        self.status = status
        self.sections: tuple[str, ...] = ()
        self.calls: list[tuple[Path, Path | None, str]] = []

    def export_sections(
        self,
        sections,
        docx_path: str | Path,
        logo_path: str | Path | None = None,
        report_date_override: str = "",
    ) -> ReportExportResult:
        target = Path(docx_path)
        self.sections = tuple(sections)
        self.calls.append((target, Path(logo_path) if logo_path else None, report_date_override))
        if self.status != "success":
            return ReportExportResult(status="error", output_path=target, error_message="word failed")

        target.write_text("\n\n".join(self.sections), encoding="utf-8")
        return ReportExportResult(status="success", output_path=target)


class FakeQueuePDFExporter:
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


class FakeQueueManualWordExporter:
    def __init__(self, status: str = "success") -> None:
        self.status = status
        self.sections: tuple[str, ...] = ()
        self.calls: list[tuple[Path, str, tuple[PerformanceRequest, ...]]] = []

    def export_sections(
        self,
        sections,
        docx_path: str | Path,
        template_id: str,
        requests=(),
    ) -> ReportExportResult:
        target = Path(docx_path)
        self.sections = tuple(sections)
        self.calls.append((target, template_id, tuple(requests)))
        if self.status != "success":
            return ReportExportResult(status="error", output_path=target, error_message="manual word failed")

        target.write_text("\n\n".join(self.sections), encoding="utf-8")
        return ReportExportResult(status="success", output_path=target)


class QueueReportExporterTests(unittest.TestCase):
    def test_export_merges_successful_outputs_in_queue_order(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            word_exporter = FakeQueueWordExporter()
            pdf_exporter = FakeQueuePDFExporter()
            exporter = QueueReportExporter(
                root / "output",
                word_exporter=word_exporter,
                pdf_exporter=pdf_exporter,
                manual_word_exporter=FakeQueueManualWordExporter(),
            )
            first = _successful_result(root / "run1", "job_01", "ELEVATION 1000 FT\nFIRST\nELEVATION 1500 FT\nFIRST EXTRA")
            second = _successful_result(root / "run2", "job_02", "HEADER\nELEVATION 2000 FT\nSECOND")

            result = exporter.export((first, second))

            self.assertTrue(result.succeeded, result.error_message)
            self.assertTrue(result.run_dir and result.run_dir.exists())
            self.assertTrue(result.merged_output_path and result.merged_output_path.exists())
            merged = result.merged_output_path.read_text(encoding="utf-8")
            self.assertLess(merged.index("SCENARIO 01: job_01"), merged.index("SCENARIO 02: job_02"))
            self.assertEqual(len(word_exporter.sections), 3)
            self.assertIn("FIRST", word_exporter.sections[0])
            self.assertIn("FIRST EXTRA", word_exporter.sections[1])
            self.assertIn("SECOND", word_exporter.sections[2])
            for section in word_exporter.sections:
                self.assertNotIn("SCENARIO 01:", section)
                self.assertNotIn("SCENARIO 02:", section)
                self.assertNotIn("Aircraft:", section)
                self.assertNotIn("Raw output:", section)
                self.assertNotIn("Section:", section)
            self.assertTrue(result.word_report and result.word_report.succeeded)
            self.assertTrue(result.pdf_report and result.pdf_report.succeeded)

    def test_export_prefers_enriched_report_output_when_available(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            word_exporter = FakeQueueWordExporter()
            exporter = QueueReportExporter(
                root / "output",
                word_exporter=word_exporter,
                pdf_exporter=FakeQueuePDFExporter(),
                manual_word_exporter=FakeQueueManualWordExporter(),
            )
            ok = _successful_result(
                root / "run1",
                "job_01",
                "ELEVATION 1000 FT\nRAW",
                report_content="ELEVATION 1000 FT\nENRICHED",
            )

            result = exporter.export((ok,))

            self.assertTrue(result.succeeded, result.error_message)
            self.assertEqual(len(word_exporter.sections), 1)
            self.assertIn("ENRICHED", word_exporter.sections[0])
            self.assertNotIn("RAW", word_exporter.sections[0])
            self.assertTrue(result.merged_output_path)
            self.assertIn("STASOUT.enriched.out", result.merged_output_path.read_text(encoding="utf-8"))

    def test_export_skips_failed_scenarios_and_reports_warning(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            word_exporter = FakeQueueWordExporter()
            exporter = QueueReportExporter(
                root / "output",
                word_exporter=word_exporter,
                pdf_exporter=FakeQueuePDFExporter(),
                manual_word_exporter=FakeQueueManualWordExporter(),
            )
            failed = PerformanceCalculationResult(
                status="error",
                request=PerformanceRequest(aircraft_code="738", airport_code="ZBAA", scenario_id="bad"),
                error_message="validation failed",
            )
            ok = _successful_result(root / "run2", "ok", "ELEVATION 2000 FT\nOK")

            result = exporter.export((failed, ok))

            self.assertTrue(result.succeeded, result.error_message)
            self.assertEqual(len(word_exporter.sections), 1)
            self.assertIn("Skipped scenario 01 (bad): validation failed", result.warnings)

    def test_export_returns_error_when_no_successful_raw_output_exists(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            exporter = QueueReportExporter(
                Path(temp_dir) / "output",
                word_exporter=FakeQueueWordExporter(),
                pdf_exporter=FakeQueuePDFExporter(),
                manual_word_exporter=FakeQueueManualWordExporter(),
            )
            failed = PerformanceCalculationResult(
                status="error",
                request=PerformanceRequest(aircraft_code="738", airport_code="ZBAA", scenario_id="bad"),
                error_message="failed",
            )

            result = exporter.export((failed,))

            self.assertFalse(result.succeeded)
            self.assertIn("No successful scenario raw output", result.error_message)
            self.assertIsNone(result.run_dir)

    def test_word_or_pdf_failure_is_returned_as_warning(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            exporter = QueueReportExporter(
                root / "output",
                word_exporter=FakeQueueWordExporter(status="success"),
                pdf_exporter=FakeQueuePDFExporter(status="error"),
                manual_word_exporter=FakeQueueManualWordExporter(),
            )
            ok = _successful_result(root / "run1", "ok", "ELEVATION 1000 FT\nOK")

            result = exporter.export((ok,))

            self.assertTrue(result.succeeded)
            self.assertTrue(result.pdf_report)
            self.assertFalse(result.pdf_report.succeeded)
            self.assertIn("Queue temporary takeoff PDF report was not generated: pdf failed", result.warnings)

    def test_queue_temporary_report_uses_shared_report_date_without_changing_merged_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            word_exporter = FakeQueueWordExporter()
            exporter = QueueReportExporter(
                root / "output",
                word_exporter=word_exporter,
                pdf_exporter=FakeQueuePDFExporter(),
                manual_word_exporter=FakeQueueManualWordExporter(),
            )
            ok = _successful_result(
                root / "run1",
                "ok",
                "ELEVATION 1000 FT\n      738         CFM56-7B26                                DATED 19-MAY-2026",
                report_date_override="04-APR-2026",
            )

            result = exporter.export((ok,))

            self.assertTrue(result.succeeded, result.error_message)
            self.assertEqual(word_exporter.calls[0][2], "04-APR-2026")
            self.assertTrue(result.merged_output_path)
            self.assertIn("DATED 19-MAY-2026", result.merged_output_path.read_text(encoding="utf-8"))

    def test_export_generates_manual_report_when_successful_outputs_share_template(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            word_exporter = FakeQueueWordExporter()
            pdf_exporter = FakeQueuePDFExporter()
            manual_word_exporter = FakeQueueManualWordExporter()
            exporter = QueueReportExporter(
                root / "output",
                word_exporter=word_exporter,
                pdf_exporter=pdf_exporter,
                manual_word_exporter=manual_word_exporter,
            )
            first = _successful_result(root / "run1", "job_01", "ELEVATION 1000 FT\nFIRST", "738_normal")
            second = _successful_result(root / "run2", "job_02", "ELEVATION 2000 FT\nSECOND", "738_normal")

            result = exporter.export((first, second))

            self.assertTrue(result.succeeded, result.error_message)
            self.assertIsNone(result.word_report)
            self.assertIsNone(result.pdf_report)
            self.assertTrue(result.manual_word_report and result.manual_word_report.succeeded)
            self.assertTrue(result.manual_pdf_report and result.manual_pdf_report.succeeded)
            self.assertEqual(result.manual_report_template_id, "738_normal")
            self.assertEqual(word_exporter.calls, [])
            self.assertEqual(manual_word_exporter.calls[0][1], "738_normal")
            self.assertEqual(len(manual_word_exporter.calls[0][2]), 2)
            self.assertEqual(len(pdf_exporter.calls), 1)

    def test_export_rejects_mixed_manual_templates_in_one_queue_report(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            manual_word_exporter = FakeQueueManualWordExporter()
            exporter = QueueReportExporter(
                root / "output",
                word_exporter=FakeQueueWordExporter(),
                pdf_exporter=FakeQueuePDFExporter(),
                manual_word_exporter=manual_word_exporter,
            )
            first = _successful_result(root / "run1", "job_01", "ELEVATION 1000 FT\nFIRST", "738_normal")
            second = _successful_result(root / "run2", "job_02", "ELEVATION 2000 FT\nSECOND", "777f_bump")

            result = exporter.export((first, second))

            self.assertTrue(result.succeeded, result.error_message)
            self.assertTrue(result.manual_word_report)
            self.assertFalse(result.manual_word_report.succeeded)
            self.assertIn("同一机型、同一推力", result.manual_word_report.error_message)
            self.assertEqual(manual_word_exporter.calls, [])

    def test_format_queue_report_summary_includes_paths_and_warnings(self) -> None:
        run_dir = Path("output/queue")
        report = QueueReportResult(
            status="success",
            run_dir=run_dir,
            merged_output_path=run_dir / "STAS_QUEUE.out",
            word_report=ReportExportResult(status="success", output_path=run_dir / "队列_临时起飞分析.docx"),
            pdf_report=ReportExportResult(status="error", output_path=run_dir / "队列_临时起飞分析.pdf", error_message="pdf failed"),
            manual_word_report=ReportExportResult(status="success", output_path=run_dir / "队列_手册起飞分析.docx"),
            warnings=("warning text",),
        )

        summary = format_queue_report_summary(report)

        self.assertIn("STAS_QUEUE.out", summary)
        self.assertIn("队列_临时起飞分析.docx", summary)
        self.assertIn("队列_手册起飞分析.docx", summary)
        self.assertIn("pdf failed", summary)
        self.assertIn("warning text", summary)


def _successful_result(
    run_dir: Path,
    scenario_id: str,
    raw_content: str,
    manual_report_template_id: str = "",
    report_content: str | None = None,
    report_date_override: str = "",
) -> PerformanceCalculationResult:
    run_dir.mkdir(parents=True, exist_ok=True)
    input_path = run_dir / "STASINP"
    raw_output_path = run_dir / "STASOUT.out"
    input_path.write_text("input", encoding="utf-8")
    raw_output_path.write_text(raw_content, encoding="utf-8")
    report_output_path = None
    if report_content is not None:
        report_output_path = run_dir / "STASOUT.enriched.out"
        report_output_path.write_text(report_content, encoding="utf-8")
    request = PerformanceRequest(
        aircraft_code="738",
        airport_code="ZBAA",
        runways=("18L",),
        scenario_id=scenario_id,
        runway_condition="DRY",
        bleed="AUTO",
        anti_icing="0",
        manual_report_template_id=manual_report_template_id,
        report_date_override=report_date_override,
    )
    return PerformanceCalculationResult(
        status="success",
        request=request,
        stas_run=StasRunResult(
            status="success",
            run_dir=run_dir,
            input_path=input_path,
            raw_output_path=raw_output_path,
            report_output_path=report_output_path,
        ),
    )


if __name__ == "__main__":
    unittest.main()
