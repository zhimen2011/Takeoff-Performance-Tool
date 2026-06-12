"""Service for single-point takeoff weight reverse calculations."""

from __future__ import annotations

import shutil
from dataclasses import replace
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Protocol

from stas_app.models.request import PerformanceRequest
from stas_app.models.result import StasRunResult
from stas_app.models.runway import Runway, RunwayDataset
from stas_app.models.single_point import (
    ATM_MODE_FIXED,
    ATM_MODE_MAX,
    SinglePointCalculationResult,
    SinglePointSectionResult,
    SinglePointTakeoffRequest,
)
from stas_app.parsers.stas_table_parser import is_stas_null, parse_stas_table
from stas_app.services.aircraft_registry import AircraftRegistry
from stas_app.services.runway_procedure_enricher import extract_runway_display_procedures
from stas_app.services.single_point_input_builder import SinglePointInputBuilder
from stas_app.services.validation import NUMBER_PATTERN, ValidationError


TABLE_FILENAME = "STASTBL"
ATM_WEIGHT_MISMATCH_NOTICE = "The input assumed temperature could not be achieved at the requested takeoff weight"
FLAP_OPTIONS_BY_AIRCRAFT = {
    "777F": ("5", "15", "20"),
    "738": ("1", "5", "10", "15", "25"),
}
DEFAULT_FLAP_BY_AIRCRAFT = {
    "777F": "15",
    "738": "5",
}


class StasEngineLike(Protocol):
    """Minimal interface needed from the STAS engine."""

    def run(self, request: PerformanceRequest, input_content: str) -> StasRunResult:
        ...


class RunwayRuntimeFilePreparerLike(Protocol):
    """Minimal interface for preparing STAS APTRWY.RWY before a calculation."""

    def prepare_for_airports(self, airport_codes: tuple[str, ...]) -> Path:
        ...


class SinglePointTakeoffService:
    """Coordinate STAS VARIABLE calculations for one runway and one takeoff weight."""

    def __init__(
        self,
        aircraft_registry: AircraftRegistry,
        runway_dataset: RunwayDataset,
        input_builder: SinglePointInputBuilder,
        stas_engine: StasEngineLike,
        stas_work_dir: str | Path,
        runway_runtime_file_preparer: RunwayRuntimeFilePreparerLike | None = None,
        runway_procedure_file: str | Path | None = None,
        table_filename: str = TABLE_FILENAME,
    ) -> None:
        self.aircraft_registry = aircraft_registry
        self.runway_dataset = runway_dataset
        self.input_builder = input_builder
        self.stas_engine = stas_engine
        self.stas_work_dir = Path(stas_work_dir)
        self.runway_runtime_file_preparer = runway_runtime_file_preparer
        self.runway_procedure_file = Path(runway_procedure_file) if runway_procedure_file is not None else None
        self.table_filename = self._ensure_simple_filename(table_filename, "STAS table filename")

    def calculate(self, request: SinglePointTakeoffRequest) -> SinglePointCalculationResult:
        """Run FULL and ATM calculations and return display-ready values."""

        try:
            validated_request = self._validate_request(request)
            aircraft = self.aircraft_registry.get(validated_request.aircraft_code)
            self._prepare_runtime_runway_file(validated_request)
            procedure = self._procedure_for_request(validated_request)
            runway = self.runway_dataset.get_runway(validated_request.airport_code, validated_request.runway)
            full_input = self.input_builder.build_full(validated_request, aircraft)
            atm_input = self.input_builder.build_atm(validated_request, aircraft)

            warnings: list[str] = []
            full_run, full_table = self._run_table(validated_request, "FULL", full_input)
            if not full_run.succeeded and not full_table.exists():
                return self._error(validated_request, full_run.error_message or "FULL calculation failed", full_run)
            if not full_run.succeeded:
                warnings.extend(self._warnings_from_run("FULL", full_run))

            atm_run, atm_table = self._run_table(validated_request, "ATM", atm_input)
            if not atm_run.succeeded and not atm_table.exists():
                return self._error(
                    validated_request,
                    atm_run.error_message or "ATM calculation failed",
                    full_run,
                    atm_run,
                    full_table,
                )
            if not atm_run.succeeded:
                warnings.extend(self._warnings_from_run("ATM", atm_run))

            full_row = self._target_row(parse_stas_table(full_table), validated_request.takeoff_weight_kg, "FULL")
            atm_row = self._target_row(parse_stas_table(atm_table), validated_request.takeoff_weight_kg, "ATM")
            full_weight_kg, full_notice = self._section_weight("FULL", full_row, validated_request.takeoff_weight_kg)
            atm_weight_kg, atm_notice = self._section_weight("ATM", atm_row, validated_request.takeoff_weight_kg)
            full = self._section_from_row(
                "FULL",
                full_row,
                full_weight_kg,
                full_notice,
                validated_request.actual_temperature_c,
                full_input,
                runway,
            )
            atm_temperature = self._atm_temperature(validated_request, atm_row)
            atm = self._section_from_row("ATM", atm_row, atm_weight_kg, atm_notice, atm_temperature, atm_input, runway)
        except (ValidationError, FileNotFoundError, NotADirectoryError, OSError, ValueError, KeyError) as exc:
            return SinglePointCalculationResult(status="error", request=request, error_message=str(exc))

        return SinglePointCalculationResult(
            status="success",
            request=validated_request,
            full=full,
            atm=atm,
            full_run=full_run,
            atm_run=atm_run,
            full_table_path=full_table,
            atm_table_path=atm_table,
            engine_failure_procedure_title=procedure.title if procedure else "",
            engine_failure_procedure_detail=procedure.detail if procedure else "",
            warnings=tuple(warnings),
        )

    def _run_table(
        self,
        request: SinglePointTakeoffRequest,
        label: str,
        input_content: str,
    ) -> tuple[StasRunResult, Path]:
        self._remove_stale_table()
        run_request = self._performance_request(request, label)
        stas_run = self.stas_engine.run(run_request, input_content)
        archived_table = stas_run.run_dir / self.table_filename

        work_table = self.stas_work_dir / self.table_filename
        if not work_table.exists():
            if not stas_run.succeeded:
                return stas_run, archived_table
            return (
                replace(
                    stas_run,
                    status="error",
                    error_message=f"STAS did not generate table file: {self.table_filename}",
                ),
                archived_table,
            )

        shutil.copy2(work_table, archived_table)
        return stas_run, archived_table

    def _warnings_from_run(self, label: str, stas_run: StasRunResult) -> list[str]:
        message = stas_run.error_message or "STAS returned an error status"
        if stas_run.stas_error.strip():
            compact_error = " ".join(stas_run.stas_error.split())
            message = f"{message}: {compact_error}"
        return [f"{label} STAS warning retained because target STASTBL row was available: {message}"]

    def _validate_request(self, request: SinglePointTakeoffRequest) -> SinglePointTakeoffRequest:
        aircraft_code = request.aircraft_code.strip()
        if not aircraft_code:
            raise ValidationError("Aircraft must be selected")
        try:
            aircraft = self.aircraft_registry.get(aircraft_code)
            aircraft.get_thrust_option(request.thrust_option)
        except KeyError as exc:
            raise ValidationError(f"Unsupported aircraft: {request.aircraft_code}") from exc
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc

        airport_code = request.airport_code.strip().upper()
        if not airport_code:
            raise ValidationError("Airport must be selected")
        if not self.runway_dataset.airport_exists(airport_code):
            raise ValidationError(f"Airport does not exist in runway data: {airport_code}")

        runway = request.runway.strip().upper()
        if not runway:
            raise ValidationError("Runway must be selected")
        if runway not in set(self.runway_dataset.get_runway_ids(airport_code)):
            raise ValidationError(f"Runway {runway} does not belong to airport {airport_code}")

        takeoff_weight_kg = self._positive_number(request.takeoff_weight_kg, "takeoff weight")
        actual_temperature_c = self._number(request.actual_temperature_c, "actual temperature")
        wind_kt = self._number(request.wind_kt, "wind")
        qnh_ref = None if request.qnh_ref is None else self._positive_number(request.qnh_ref, "QNH")

        atm_mode = request.atm_mode.strip().upper() or ATM_MODE_MAX
        if atm_mode not in {ATM_MODE_MAX, ATM_MODE_FIXED}:
            raise ValidationError(f"Unsupported ATM mode: {request.atm_mode}")
        assumed_temperature_c = request.assumed_temperature_c
        if atm_mode == ATM_MODE_FIXED:
            if assumed_temperature_c is None:
                raise ValidationError("Assumed temperature is required when ATM mode is fixed")
            assumed_temperature_c = self._number(assumed_temperature_c, "assumed temperature")

        aircraft_key = _aircraft_key(aircraft.code)
        flap_setting = self._flap_setting(request.flap_setting, aircraft_key)

        return SinglePointTakeoffRequest(
            aircraft_code=aircraft_code,
            airport_code=airport_code,
            runway=runway,
            takeoff_weight_kg=takeoff_weight_kg,
            actual_temperature_c=actual_temperature_c,
            wind_kt=wind_kt,
            qnh_ref=qnh_ref,
            scenario_id=request.scenario_id.strip(),
            runway_condition=request.runway_condition.strip() or "DRY",
            contamination_depth=request.contamination_depth.strip(),
            bleed=request.bleed.strip(),
            anti_icing=request.anti_icing.strip() or "0",
            derate=request.derate.strip(),
            thrust_option=request.thrust_option,
            flap_setting=flap_setting,
            improved_climb=bool(request.improved_climb),
            atm_mode=atm_mode,
            assumed_temperature_c=assumed_temperature_c,
        )

    def _flap_setting(self, value: str, aircraft_key: str) -> str:
        options = FLAP_OPTIONS_BY_AIRCRAFT.get(aircraft_key)
        if options is None:
            raise ValidationError(f"Unsupported aircraft flap options: {aircraft_key}")

        token = str(value).strip().upper()
        if token.startswith("FLAP "):
            token = token.split(maxsplit=1)[1].strip()
        elif token.startswith("FLAP"):
            token = token[4:].strip()
        if not token:
            token = DEFAULT_FLAP_BY_AIRCRAFT[aircraft_key]

        if token not in options:
            allowed = ", ".join(f"FLAP {option}" for option in options)
            raise ValidationError(f"Unsupported flap setting for {aircraft_key}: FLAP {token}. Allowed: {allowed}")
        return token

    def _section_from_row(
        self,
        label: str,
        row: dict[str, float],
        takeoff_weight_kg: float | None,
        notice: str,
        temperature_c: float | None,
        input_content: str,
        runway: Runway | None,
    ) -> SinglePointSectionResult:
        popt_012 = self._scap_input_section_value(input_content, "POPT", 12, f"{label} POPT(012)")
        popt_013 = self._scap_input_section_value(input_content, "POPT", 13, f"{label} POPT(013)")
        return SinglePointSectionResult(
            label=label,
            takeoff_weight_kg=takeoff_weight_kg,
            notice=notice,
            temperature_c=temperature_c,
            v1=self._rounded_required(row, "CLIMIT(019)", f"{label} V1"),
            vr=self._rounded_required(row, "CLIMIT(006)", f"{label} VR"),
            v2=self._rounded_required(row, "CLIMIT(005)", f"{label} V2"),
            vref30=self._rounded_required(row, "SPOUTA(005)", f"{label} VREF30"),
            takeoff_thrust=self._one_decimal(row.get("CLIMIT(028)")),
            reduction_percent=self._one_decimal(row.get("SPOUTA(032)")),
            accel_height_ft=self._rounded_required(row, "ACCSEG(002)", f"{label} ACCEL HT"),
            takeoff_run_m=self._one_decimal(row.get("CLIMIT(022)")),
            takeoff_distance_m=self._one_decimal(row.get("CLIMIT(023)")),
            accelerate_stop_distance_m=self._one_decimal(row.get("CLIMIT(024)")),
            ae_go_m=self._rounded_sum(row.get("CLIMIT(026)"), popt_012),
            eo_go_m=self._rounded_sum(row.get("CLIMIT(023)"), popt_012),
            accel_stop_m=self._rounded_sum(row.get("CLIMIT(024)"), popt_013),
            tora_m=runway.tora_m if runway else None,
            toda_m=runway.toda_m if runway else None,
            asda_m=runway.asda_m if runway else None,
            slope_percent=runway.slope_percent if runway else None,
        )

    def _section_weight(
        self,
        label: str,
        row: dict[str, float],
        requested_weight_kg: float,
    ) -> tuple[int, str]:
        value = row.get("CLIMIT(001)")
        if is_stas_null(value):
            raise ValueError(f"{label} CLIMIT(001) was not returned by STAS")

        actual_weight_kg = _round_half_up(value)
        requested_weight_kg_rounded = _round_half_up(requested_weight_kg)
        if actual_weight_kg == requested_weight_kg_rounded:
            return actual_weight_kg, ""

        if label.upper() == "FULL":
            raise ValueError(
                "FULL 计算出错："
                f"STAS 返回的实际起飞重量 {actual_weight_kg:g} KG "
                f"与输入 TOGW {requested_weight_kg_rounded:g} KG 不一致。"
            )

        return actual_weight_kg, ATM_WEIGHT_MISMATCH_NOTICE

    def _atm_temperature(self, request: SinglePointTakeoffRequest, row: dict[str, float]) -> float | None:
        if request.atm_mode == ATM_MODE_FIXED:
            return request.assumed_temperature_c
        value = row.get("CLIMIT(044)")
        if is_stas_null(value):
            raise ValueError("ATM maximum assumed temperature was not returned by STAS")
        return value

    def _target_row(
        self,
        rows: list[dict[str, float]],
        target_weight_kg: float,
        label: str,
    ) -> dict[str, float]:
        if not rows:
            raise ValueError(f"{label} STASTBL did not contain any data rows")

        for row in rows:
            weight = row.get("POPT(024)")
            if weight is not None and abs(weight - target_weight_kg) < 0.5:
                return row

        raise ValueError(f"{label} STASTBL did not contain target takeoff weight {target_weight_kg:g} KG")

    def _rounded_required(self, row: dict[str, float], key: str, label: str) -> int:
        value = row.get(key)
        if is_stas_null(value):
            raise ValueError(f"{label} was not returned by STAS")
        return _round_half_up(value)

    def _one_decimal(self, value: float | None) -> float | None:
        if is_stas_null(value):
            return None
        return float(Decimal(str(value)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))

    def _rounded_sum(self, value: float | None, addend: float) -> int | None:
        if is_stas_null(value):
            return None
        total = Decimal(str(value)) + Decimal(str(addend))
        return int(total.quantize(Decimal("1"), rounding=ROUND_HALF_UP))

    def _scap_input_section_value(self, input_content: str, section_name: str, index: int, label: str) -> float:
        values: list[str] = []
        in_section = False
        section_header = section_name.strip().upper()

        for raw_line in input_content.splitlines():
            line = raw_line.strip()
            if not line:
                continue

            if not in_section:
                if line.upper() == section_header:
                    in_section = True
                continue

            data_part = line.split("/", maxsplit=1)[0].strip()
            if data_part:
                values.extend(data_part.split())
            if "/" in line:
                break

        if not in_section or len(values) < index:
            raise ValueError(f"{label} was not found in rendered STAS input")

        token = values[index - 1]
        try:
            return float(token)
        except ValueError as exc:
            raise ValueError(f"{label} must be numeric in rendered STAS input: {token}") from exc

    def _performance_request(self, request: SinglePointTakeoffRequest, label: str) -> PerformanceRequest:
        scenario_id = request.scenario_id or "single_point"
        return PerformanceRequest(
            aircraft_code=request.aircraft_code,
            airport_code=request.airport_code,
            runways=(request.runway,),
            scenario_id=f"{scenario_id}_{label.lower()}",
            runway_condition=request.runway_condition,
            contamination_depth=request.contamination_depth,
            bleed=request.bleed,
            anti_icing=request.anti_icing,
            derate=request.derate,
            qnh_ref="" if request.qnh_ref is None else str(request.qnh_ref),
            thrust_option=request.thrust_option,
        )

    def _prepare_runtime_runway_file(self, request: SinglePointTakeoffRequest) -> None:
        if self.runway_runtime_file_preparer is None:
            return
        self.runway_runtime_file_preparer.prepare_for_airports((request.airport_code,))

    def _procedure_for_request(self, request: SinglePointTakeoffRequest):
        if self.runway_procedure_file is None:
            return None
        try:
            procedures = extract_runway_display_procedures(self.runway_procedure_file)
        except (OSError, ValueError):
            return None
        return procedures.get((request.airport_code.upper(), request.runway.upper()))

    def _remove_stale_table(self) -> None:
        path = self.stas_work_dir / self.table_filename
        if path.exists():
            path.unlink()

    def _error(
        self,
        request: SinglePointTakeoffRequest,
        message: str,
        full_run: StasRunResult | None = None,
        atm_run: StasRunResult | None = None,
        full_table_path: Path | None = None,
        atm_table_path: Path | None = None,
    ) -> SinglePointCalculationResult:
        return SinglePointCalculationResult(
            status="error",
            request=request,
            full_run=full_run,
            atm_run=atm_run,
            full_table_path=full_table_path,
            atm_table_path=atm_table_path,
            error_message=message,
        )

    def _positive_number(self, value: float | int | str, field_name: str) -> float:
        number = self._number(value, field_name)
        if number <= 0:
            raise ValidationError(f"{field_name} must be positive")
        return number

    def _number(self, value: float | int | str, field_name: str) -> float:
        token = str(value).strip()
        if not NUMBER_PATTERN.match(token):
            raise ValidationError(f"Invalid {field_name} value: {value}")
        return float(token)

    def _ensure_simple_filename(self, filename: str, label: str) -> str:
        if Path(filename).name != filename:
            raise ValueError(f"{label} must not include path separators: {filename}")
        return filename


def _round_half_up(value: float) -> int:
    return int(Decimal(str(value)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _aircraft_key(aircraft_code: str) -> str:
    code = aircraft_code.strip().upper()
    if code in {"777F", "B777F"}:
        return "777F"
    if code in {"738", "737-800", "737800", "737-800W", "B738"}:
        return "738"
    return code
