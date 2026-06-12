"""Service for invoking the external STAS executable."""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

from stas_app.models.request import PerformanceRequest
from stas_app.models.result import StasRunResult
from stas_app.storage.output_manager import OutputManager


@dataclass(frozen=True)
class StasEngineConfig:
    """Runtime settings needed to call STAS."""

    executable_path: str | Path
    work_dir: str | Path
    output_root: str | Path
    executable_args: tuple[str, ...] = field(default_factory=tuple)
    input_filename: str = "STASINP"
    output_filename: str = "STASOUT.out"
    error_filename: str = "STASERR"
    timeout_seconds: int = 1200


class StasEngine:
    """Run STAS with a generated input file and archive the raw result."""

    def __init__(self, config: StasEngineConfig, output_manager: OutputManager | None = None) -> None:
        self.config = config
        self.executable_path = Path(config.executable_path)
        self.work_dir = Path(config.work_dir)
        self.output_manager = output_manager or OutputManager(config.output_root)

        self._ensure_simple_filename(config.input_filename, "input filename")
        self._ensure_simple_filename(config.output_filename, "output filename")
        self._ensure_simple_filename(config.error_filename, "error filename")

    def run(self, request: PerformanceRequest, input_content: str) -> StasRunResult:
        self._validate_runtime_paths()

        run_dir = self.output_manager.create_run_directory(request)
        work_input = self.work_dir / self.config.input_filename
        work_output = self.work_dir / self.config.output_filename
        work_error = self.work_dir / self.config.error_filename
        archived_input = run_dir / self.config.input_filename

        self._remove_stale_file(work_output)
        self._remove_stale_file(work_error)

        work_input.write_text(input_content, encoding="utf-8")
        shutil.copy2(work_input, archived_input)

        started = time.perf_counter()
        try:
            completed = subprocess.run(
                self._command(),
                input=f"{self.config.input_filename}\n{self.config.output_filename}\n",
                cwd=str(self.work_dir),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=self._runtime_env(),
                timeout=self.config.timeout_seconds,
                check=False,
                **self._subprocess_run_options(),
            )
        except subprocess.TimeoutExpired as exc:
            elapsed = time.perf_counter() - started
            result = StasRunResult(
                status="timeout",
                run_dir=run_dir,
                input_path=archived_input,
                stdout=self._as_text(exc.stdout),
                stderr=self._as_text(exc.stderr),
                elapsed_seconds=elapsed,
                error_message=f"STAS execution timed out after {self.config.timeout_seconds} seconds",
            )
            metadata_path = self._write_result_metadata(request, result)
            return self._with_metadata_path(result, metadata_path)

        elapsed = time.perf_counter() - started
        archived_output = self._archive_optional_file(work_output, run_dir)
        archived_error = self._archive_optional_file(work_error, run_dir)
        stas_error = self._read_optional_text(archived_error)

        status, error_message = self._determine_status(completed.returncode, archived_output, stas_error)
        result = StasRunResult(
            status=status,
            run_dir=run_dir,
            input_path=archived_input,
            raw_output_path=archived_output,
            stas_error_path=archived_error,
            return_code=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
            stas_error=stas_error,
            elapsed_seconds=elapsed,
            error_message=error_message,
        )
        metadata_path = self._write_result_metadata(request, result)
        return self._with_metadata_path(result, metadata_path)

    def _validate_runtime_paths(self) -> None:
        if not self.executable_path.exists():
            raise FileNotFoundError(f"STAS executable does not exist: {self.executable_path}")

        if not self.work_dir.exists():
            raise FileNotFoundError(f"STAS work directory does not exist: {self.work_dir}")

        if not self.work_dir.is_dir():
            raise NotADirectoryError(f"STAS work directory is not a directory: {self.work_dir}")

    def _command(self) -> list[str]:
        return [str(self.executable_path), *self.config.executable_args]

    def _runtime_env(self) -> dict[str, str]:
        env = os.environ.copy()
        temp_dir = str(self.work_dir.resolve())
        env["TEMP"] = temp_dir
        env["TMP"] = temp_dir
        return env

    def _subprocess_run_options(self) -> dict[str, int]:
        if os.name != "nt":
            return {}

        create_no_window = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        if not create_no_window:
            return {}

        return {"creationflags": create_no_window}

    def _determine_status(
        self,
        return_code: int,
        archived_output: Path | None,
        stas_error: str,
    ) -> tuple[str, str]:
        if return_code != 0:
            return "error", f"STAS exited with return code {return_code}"

        if archived_output is None:
            return "error", f"STAS did not generate output file: {self.config.output_filename}"

        if stas_error.strip():
            return "error", "STAS generated an error file"

        return "success", ""

    def _write_result_metadata(self, request: PerformanceRequest, result: StasRunResult) -> Path:
        metadata = {
            "status": result.status,
            "scenario_id": request.scenario_id,
            "aircraft_code": request.aircraft_code,
            "airport_code": request.airport_code,
            "runways": list(request.runways),
            "runway_condition": request.runway_condition,
            "contamination_depth": request.contamination_depth,
            "bleed": request.bleed,
            "anti_icing": request.anti_icing,
            "derate": request.derate,
            "report_date_override": request.report_date_override,
            "return_code": result.return_code,
            "elapsed_seconds": result.elapsed_seconds,
            "input_path": str(result.input_path),
            "raw_output_path": str(result.raw_output_path) if result.raw_output_path else "",
            "stas_error_path": str(result.stas_error_path) if result.stas_error_path else "",
            "error_message": result.error_message,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "stas_error": result.stas_error,
        }
        return self.output_manager.write_metadata(result.run_dir, metadata)

    def _with_metadata_path(self, result: StasRunResult, metadata_path: Path) -> StasRunResult:
        return StasRunResult(
            status=result.status,
            run_dir=result.run_dir,
            input_path=result.input_path,
            raw_output_path=result.raw_output_path,
            stas_error_path=result.stas_error_path,
            metadata_path=metadata_path,
            return_code=result.return_code,
            stdout=result.stdout,
            stderr=result.stderr,
            stas_error=result.stas_error,
            elapsed_seconds=result.elapsed_seconds,
            error_message=result.error_message,
            warnings=result.warnings,
        )

    def _archive_optional_file(self, source: Path, run_dir: Path) -> Path | None:
        if not source.exists():
            return None

        destination = run_dir / source.name
        shutil.copy2(source, destination)
        return destination

    def _read_optional_text(self, path: Path | None) -> str:
        if path is None:
            return ""

        return path.read_text(encoding="utf-8", errors="replace")

    def _remove_stale_file(self, path: Path) -> None:
        if path.exists():
            path.unlink()

    def _as_text(self, value: str | bytes | None) -> str:
        if value is None:
            return ""
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="replace")
        return value

    def _ensure_simple_filename(self, filename: str, label: str) -> None:
        if Path(filename).name != filename:
            raise ValueError(f"STAS {label} must not include path separators: {filename}")
