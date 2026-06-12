from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
sys.path.insert(0, str(SRC_DIR))

from stas_app.models.request import PerformanceRequest
from stas_app.services.stas_engine import StasEngine, StasEngineConfig


FAKE_STAS = ROOT_DIR / "tests" / "fixtures" / "fake_stas.py"


class StasEngineTests(unittest.TestCase):
    def test_run_success_archives_input_output_and_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            work_dir = root / "work"
            output_root = root / "output"
            work_dir.mkdir()

            engine = self._engine(work_dir, output_root, mode="success")
            request = PerformanceRequest(aircraft_code="777F", airport_code="UNAA")

            result = engine.run(request, "TEST STAS INPUT")

            self.assertTrue(result.succeeded)
            self.assertEqual(result.return_code, 0)
            self.assertTrue(result.input_path.exists())
            self.assertTrue(result.raw_output_path and result.raw_output_path.exists())
            self.assertTrue(result.metadata_path and result.metadata_path.exists())
            self.assertIn("TEST STAS INPUT", result.raw_output_path.read_text(encoding="utf-8"))
            self.assertIn(f"TEMP={work_dir.resolve()}", result.raw_output_path.read_text(encoding="utf-8"))

            metadata = json.loads(result.metadata_path.read_text(encoding="utf-8"))
            self.assertEqual(metadata["status"], "success")
            self.assertEqual(metadata["aircraft_code"], "777F")
            self.assertEqual(metadata["airport_code"], "UNAA")

    def test_run_failure_archives_stas_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            work_dir = root / "work"
            output_root = root / "output"
            work_dir.mkdir()

            engine = self._engine(work_dir, output_root, mode="fail")
            request = PerformanceRequest(aircraft_code="738", airport_code="ZBAA")

            result = engine.run(request, "BAD STAS INPUT")

            self.assertFalse(result.succeeded)
            self.assertEqual(result.status, "error")
            self.assertEqual(result.return_code, 2)
            self.assertTrue(result.stas_error_path and result.stas_error_path.exists())
            self.assertIn("COULD NOT PROCESS", result.stas_error)

    def test_run_without_output_is_error_even_with_zero_return_code(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            work_dir = root / "work"
            output_root = root / "output"
            work_dir.mkdir()

            engine = self._engine(work_dir, output_root, mode="no-output")
            request = PerformanceRequest(aircraft_code="738", airport_code="ZBAA")

            result = engine.run(request, "INPUT")

            self.assertFalse(result.succeeded)
            self.assertEqual(result.status, "error")
            self.assertIn("did not generate output", result.error_message)
            self.assertIsNone(result.raw_output_path)

    def test_run_hides_external_stas_console_on_windows(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            work_dir = root / "work"
            output_root = root / "output"
            work_dir.mkdir()

            engine = StasEngine(
                StasEngineConfig(
                    executable_path=sys.executable,
                    work_dir=work_dir,
                    output_root=output_root,
                    timeout_seconds=10,
                )
            )
            request = PerformanceRequest(aircraft_code="738", airport_code="ZBAA")

            def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                output_path = Path(str(kwargs["cwd"])) / "STASOUT.out"
                output_path.write_text("SIMULATED STAS OUTPUT", encoding="utf-8")
                return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

            with mock.patch("stas_app.services.stas_engine.subprocess.run", side_effect=fake_run) as run_mock:
                result = engine.run(request, "INPUT")

            self.assertTrue(result.succeeded)
            run_kwargs = run_mock.call_args.kwargs
            if os.name == "nt":
                self.assertEqual(run_kwargs.get("creationflags"), subprocess.CREATE_NO_WINDOW)
            else:
                self.assertNotIn("creationflags", run_kwargs)

    def _engine(self, work_dir: Path, output_root: Path, mode: str) -> StasEngine:
        return StasEngine(
            StasEngineConfig(
                executable_path=sys.executable,
                executable_args=(str(FAKE_STAS), mode),
                work_dir=work_dir,
                output_root=output_root,
                timeout_seconds=10,
            )
        )


if __name__ == "__main__":
    unittest.main()
