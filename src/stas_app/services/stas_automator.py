"""Task-queue automation for Scenario-driven STAS calculations."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any, Protocol

from stas_app.models.request import PerformanceRequest
from stas_app.models.result import PerformanceCalculationResult
from stas_app.parsers.stas_output_parser import parse_stas_output


DEFAULT_TEMPLATE_ORDER = (
    ("DRY", "DEFAULT"),
    ("DRY", "OFF"),
    ("WET", "DEFAULT"),
    ("WET", "OFF"),
)

DEFAULT_BLEED_BY_AIRCRAFT = {
    "777F": "ON",
    "738": "AUTO",
}


class PerformanceServiceLike(Protocol):
    """Minimal service interface used by the task queue automator."""

    def calculate(self, request: PerformanceRequest) -> PerformanceCalculationResult:
        ...


class STASAutomator:
    """Run a user-defined queue of independent STAS calculation scenarios."""

    def __init__(self, performance_service: PerformanceServiceLike) -> None:
        self.performance_service = performance_service

    def run_task_queue(self, task_queue: Iterable[Mapping[str, Any]]):
        """Run each task as one independent Scenario and return a pandas DataFrame."""

        import pandas as pd

        report_rows: list[dict[str, Any]] = []
        for task_index, task in enumerate(task_queue, start=1):
            request = self.build_request(task, task_index)
            result = self.performance_service.calculate(request)
            base_row = self._base_row(task_index, task, request, result)

            if result.succeeded and result.stas_run and result.stas_run.raw_output_path:
                parsed_rows = parse_stas_output(result.stas_run.raw_output_path)
                if parsed_rows:
                    report_rows.extend({**base_row, **parsed_row} for parsed_row in parsed_rows)
                    continue

            report_rows.append(base_row)

        return pd.DataFrame(report_rows)

    def run_default_template_order(self, base_task: Mapping[str, Any]):
        """Run the old template's four-step default order for one base Scenario."""

        return self.run_task_queue(build_default_template_order(base_task))

    def build_request(self, task: Mapping[str, Any], task_index: int = 1) -> PerformanceRequest:
        """Convert a task dictionary into a single STAS performance request."""

        airport_code, runways = self._airport_and_runways(task)
        return PerformanceRequest(
            aircraft_code=str(self._first_value(task, "aircraft_code", "aircraft", "type", default="")).strip(),
            airport_code=airport_code,
            runways=runways,
            scenario_id=str(self._first_value(task, "scenario_id", "id", default=f"job_{task_index:03d}")).strip(),
            runway_condition=str(
                self._first_value(task, "runway_condition", "surface_condition", "surface", default="DRY")
            ).strip(),
            contamination_depth=str(
                self._first_value(task, "contamination_depth", "depth", "contam_depth", default="")
            ).strip(),
            bleed=str(self._first_value(task, "bleed", "air_conditioning", "air_cond", default="")).strip(),
            anti_icing=str(self._first_value(task, "anti_icing", "anti_ice", "antiIce", default="0")).strip(),
            derate=str(self._first_value(task, "derate", "derate_value", "derated", default="")).strip(),
            temperature_range=str(self._first_value(task, "temperature_range", "temps", default="")).strip(),
            wind_range=str(self._first_value(task, "wind_range", "winds", default="")).strip(),
            qnh_ref=str(self._first_value(task, "qnh_ref", "qnh", default="")).strip(),
            thrust_option=self._optional_string(self._first_value(task, "thrust_option", "thrust", default=None)),
            report_date_override=str(
                self._first_value(task, "report_date_override", "report_date", default="")
            ).strip(),
        )

    def _base_row(
        self,
        task_index: int,
        task: Mapping[str, Any],
        request: PerformanceRequest,
        result: PerformanceCalculationResult,
    ) -> dict[str, Any]:
        stas_run = result.stas_run
        return {
            "task_index": task_index,
            "scenario_id": request.scenario_id,
            "status": result.status,
            "error_message": result.error_message,
            "aircraft_code": request.aircraft_code,
            "airport_code": request.airport_code,
            "runways": ",".join(request.runways),
            "runway_condition": request.runway_condition,
            "contamination_depth": request.contamination_depth,
            "bleed": request.bleed,
            "anti_icing": request.anti_icing,
            "derate": request.derate,
            "temperature_range": request.temperature_range,
            "wind_range": request.wind_range,
            "qnh_ref": request.qnh_ref,
            "thrust_option": request.thrust_option or "",
            "report_date_override": request.report_date_override,
            "run_dir": str(stas_run.run_dir) if stas_run else "",
            "input_path": str(stas_run.input_path) if stas_run else "",
            "raw_output_path": str(stas_run.raw_output_path) if stas_run and stas_run.raw_output_path else "",
            **{f"task_{key}": value for key, value in task.items()},
        }

    def _airport_and_runways(self, task: Mapping[str, Any]) -> tuple[str, tuple[str, ...]]:
        airport_code = str(self._first_value(task, "airport_code", "airport", default="")).strip().upper()
        raw_runways = self._first_value(task, "runways", "runway", "airport_runway", default=())
        runway_values = self._as_sequence(raw_runways)
        parsed_runways: list[str] = []

        for value in runway_values:
            item = str(value).strip()
            if not item:
                continue

            parsed_airport, parsed_runway = self._parse_airport_runway(item)
            if parsed_airport and not airport_code:
                airport_code = parsed_airport
            parsed_runways.append(parsed_runway)

        return airport_code, tuple(parsed_runways)

    def _parse_airport_runway(self, value: str) -> tuple[str, str]:
        if "/" in value:
            airport, runway = value.split("/", maxsplit=1)
            return airport.strip().upper(), runway.strip().upper()

        parts = value.split()
        if len(parts) == 2 and len(parts[0]) in {3, 4}:
            return parts[0].strip().upper(), parts[1].strip().upper()

        return "", value.strip().upper()

    def _first_value(self, task: Mapping[str, Any], *keys: str, default: Any) -> Any:
        for key in keys:
            if key in task and task[key] is not None:
                return task[key]
        return default

    def _as_sequence(self, value: Any) -> tuple[Any, ...]:
        if value is None or value == "":
            return ()
        if isinstance(value, (list, tuple, set)):
            return tuple(value)
        if isinstance(value, str) and "," in value:
            return tuple(item.strip() for item in value.split(","))
        return (value,)

    def _optional_string(self, value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None


def build_default_template_order(base_task: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Build the original template order: dry/default bleed, dry/off, wet/default, wet/off."""

    base = dict(base_task)
    aircraft_code = str(_first_base_value(base, "aircraft_code", "aircraft", "type", default="")).strip()
    default_bleed = _default_bleed_for_aircraft(aircraft_code)
    base_scenario_id = str(_first_base_value(base, "scenario_id", "id", default="job")).strip() or "job"

    tasks: list[dict[str, Any]] = []
    for index, (runway_condition, bleed_choice) in enumerate(DEFAULT_TEMPLATE_ORDER, start=1):
        bleed = default_bleed if bleed_choice == "DEFAULT" else bleed_choice
        task = dict(base)
        task["scenario_id"] = f"{base_scenario_id}_{index:02d}_{runway_condition}_BLEED_{bleed}"
        task["runway_condition"] = runway_condition
        task["bleed"] = bleed
        tasks.append(task)

    return tasks


def _default_bleed_for_aircraft(aircraft_code: str) -> str:
    code = aircraft_code.strip().upper()
    if code in {"777F", "B777F"}:
        return DEFAULT_BLEED_BY_AIRCRAFT["777F"]
    if code in {"738", "737-800", "737800", "737-800W", "B738"}:
        return DEFAULT_BLEED_BY_AIRCRAFT["738"]
    return "ON"


def _first_base_value(task: Mapping[str, Any], *keys: str, default: Any) -> Any:
    for key in keys:
        if key in task and task[key] is not None:
            return task[key]
    return default
