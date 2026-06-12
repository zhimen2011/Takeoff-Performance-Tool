"""Build STAS VARIABLE input for single-point takeoff calculations."""

from __future__ import annotations

import re
from pathlib import Path

from stas_app.models.aircraft import AircraftConfig
from stas_app.models.single_point import ATM_MODE_FIXED, ATM_MODE_MAX, SinglePointTakeoffRequest
from stas_app.services.scenario_options import resolve_scenario_options


PLACEHOLDER_PATTERN = re.compile(r"\{[a-zA-Z_][a-zA-Z0-9_]*\}")
DEFAULT_COMPARISON_WEIGHTS_KG = {
    "777F": 25000,
    "738": 20000,
}
DEFAULT_FLAP_SETTINGS = {
    "777F": "15",
    "738": "5",
}


class SinglePointInputBuilder:
    """Render STAS input text for FULL and ATM single-point calculations."""

    def __init__(self, template_dir: str | Path, airport_file: str | Path) -> None:
        self.template_dir = Path(template_dir)
        self.airport_file = str(airport_file)

    def build_full(self, request: SinglePointTakeoffRequest, aircraft: AircraftConfig) -> str:
        """Build the actual-temperature FULL calculation."""

        return self._build(
            request=request,
            aircraft=aircraft,
            calculation_option="0",
            xmet001=request.actual_temperature_c,
        )

    def build_atm(self, request: SinglePointTakeoffRequest, aircraft: AircraftConfig) -> str:
        """Build the assumed-temperature ATM calculation."""

        if request.atm_mode == ATM_MODE_MAX:
            return self._build(
                request=request,
                aircraft=aircraft,
                calculation_option="4",
                xmet001=request.actual_temperature_c,
            )

        if request.atm_mode == ATM_MODE_FIXED:
            if request.assumed_temperature_c is None:
                raise ValueError("assumed_temperature_c is required when ATM mode is FIXED")
            return self._build(
                request=request,
                aircraft=aircraft,
                calculation_option="0",
                xmet001=request.assumed_temperature_c,
            )

        raise ValueError(f"Unsupported ATM mode: {request.atm_mode}")

    def comparison_weight_kg(self, aircraft_code: str) -> int:
        """Return the low comparison weight required by STAS VARIABLE output."""

        key = _aircraft_key(aircraft_code)
        return DEFAULT_COMPARISON_WEIGHTS_KG.get(key, 20000)

    def _build(
        self,
        request: SinglePointTakeoffRequest,
        aircraft: AircraftConfig,
        calculation_option: str,
        xmet001: float,
    ) -> str:
        template_path = self.template_dir / "single_point" / aircraft.template
        if not template_path.exists():
            raise FileNotFoundError(f"Single-point STAS template does not exist: {template_path}")

        template = template_path.read_text(encoding="utf-8")
        thrust_option = aircraft.get_thrust_option(request.thrust_option)
        scenario_options = resolve_scenario_options(request, aircraft.code, thrust_option.derated)
        qnh_ref = request.qnh_ref if request.qnh_ref is not None else float(aircraft.default_qnh)

        replacements = {
            "{airport_file}": str(self.airport_file),
            "{airport_runway}": self._build_airport_runway(request.airport_code, request.runway),
            "{runway_condition}": scenario_options.runway_condition,
            "{contamination_depth}": scenario_options.contamination_depth,
            "{bleed_status}": scenario_options.bleed_status,
            "{anti_icing}": scenario_options.anti_icing,
            "{derated}": scenario_options.derated,
            "{thrust_label}": thrust_option.thrust_label,
            "{qnh_ref}": _format_number(qnh_ref),
            "{qnh_ref_description}": f"QNHREF = {_format_number(qnh_ref)}",
            "{calculation_option}": calculation_option,
            "{improved_climb_option}": "0" if request.improved_climb else "1",
            "{flap_setting}": _format_number(request.flap_setting or self.default_flap_setting(aircraft.code)),
            "{comparison_weight_kg}": _format_number(self.comparison_weight_kg(aircraft.code)),
            "{takeoff_weight_kg}": _format_number(request.takeoff_weight_kg),
            "{actual_temperature_c}": _format_number(request.actual_temperature_c),
            "{xmet001_temperature_c}": _format_number(xmet001),
            "{wind_kt}": _format_number(request.wind_kt),
        }

        content = template
        for placeholder, value in replacements.items():
            content = content.replace(placeholder, value)

        unresolved = sorted(set(PLACEHOLDER_PATTERN.findall(content)))
        if unresolved:
            raise ValueError(f"Unresolved template placeholders: {', '.join(unresolved)}")

        return content

    def _build_airport_runway(self, airport_code: str, runway: str) -> str:
        return f"{airport_code.strip().upper()}/{runway.strip().upper()}"

    def default_flap_setting(self, aircraft_code: str) -> str:
        key = _aircraft_key(aircraft_code)
        return DEFAULT_FLAP_SETTINGS.get(key, "5")


def _format_number(value: float | int | str) -> str:
    number = float(value)
    if number.is_integer():
        return str(int(number))
    return f"{number:.10g}"


def _aircraft_key(aircraft_code: str) -> str:
    code = aircraft_code.strip().upper()
    if code in {"777F", "B777F"}:
        return "777F"
    if code in {"738", "737-800", "737800", "737-800W", "B738"}:
        return "738"
    return code
