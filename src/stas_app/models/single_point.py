"""Models for single-point takeoff calculations."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from stas_app.models.result import StasRunResult


ATM_MODE_MAX = "MAX"
ATM_MODE_FIXED = "FIXED"


@dataclass(frozen=True)
class SinglePointTakeoffRequest:
    """User inputs for one takeoff weight reverse calculation."""

    aircraft_code: str
    airport_code: str
    runway: str
    takeoff_weight_kg: float
    actual_temperature_c: float
    wind_kt: float
    qnh_ref: float | None = None
    scenario_id: str = ""
    runway_condition: str = "DRY"
    contamination_depth: str = ""
    bleed: str = ""
    anti_icing: str = "0"
    derate: str = ""
    thrust_option: str | None = None
    flap_setting: str = ""
    improved_climb: bool = True
    atm_mode: str = ATM_MODE_MAX
    assumed_temperature_c: float | None = None


@dataclass(frozen=True)
class SinglePointSectionResult:
    """One displayed result section, such as FULL or ATM."""

    label: str
    takeoff_weight_kg: float | None = None
    notice: str = ""
    temperature_c: float | None = None
    v1: int | None = None
    vr: int | None = None
    v2: int | None = None
    vref30: int | None = None
    takeoff_thrust: float | None = None
    reduction_percent: float | None = None
    accel_height_ft: int | None = None
    takeoff_run_m: float | None = None
    takeoff_distance_m: float | None = None
    accelerate_stop_distance_m: float | None = None
    ae_go_m: int | None = None
    eo_go_m: int | None = None
    accel_stop_m: int | None = None
    tora_m: float | None = None
    toda_m: float | None = None
    asda_m: float | None = None
    slope_percent: float | None = None


@dataclass(frozen=True)
class SinglePointCalculationResult:
    """Complete result for the single-point takeoff calculation."""

    status: str
    request: SinglePointTakeoffRequest
    full: SinglePointSectionResult | None = None
    atm: SinglePointSectionResult | None = None
    full_run: StasRunResult | None = None
    atm_run: StasRunResult | None = None
    full_table_path: Path | None = None
    atm_table_path: Path | None = None
    engine_failure_procedure_title: str = ""
    engine_failure_procedure_detail: str = ""
    error_message: str = ""
    warnings: tuple[str, ...] = field(default_factory=tuple)

    @property
    def succeeded(self) -> bool:
        return self.status == "success"
