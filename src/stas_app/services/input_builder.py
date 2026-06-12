"""Build STAS input text from aircraft templates and user parameters."""

from __future__ import annotations

import re
from pathlib import Path

from stas_app.models.aircraft import AircraftConfig
from stas_app.models.request import PerformanceRequest
from stas_app.services.scenario_options import resolve_scenario_options


PLACEHOLDER_PATTERN = re.compile(r"\{[a-zA-Z_][a-zA-Z0-9_]*\}")


class StasInputBuilder:
    """Render a STAS input file for a validated performance request."""

    def __init__(self, template_dir: str | Path, airport_file: str | Path) -> None:
        self.template_dir = Path(template_dir)
        self.airport_file = str(airport_file)

    def build(self, request: PerformanceRequest, aircraft: AircraftConfig) -> str:
        template_path = self.template_dir / aircraft.template
        if not template_path.exists():
            raise FileNotFoundError(f"STAS template does not exist: {template_path}")

        template = template_path.read_text(encoding="utf-8")
        thrust_option = aircraft.get_thrust_option(request.thrust_option)
        scenario_options = resolve_scenario_options(request, aircraft.code, thrust_option.derated)
        qnh_ref = request.qnh_ref or aircraft.default_qnh

        replacements = {
            "{airport_file}": str(self.airport_file),
            "{airport_runway}": self._build_airport_runway(request.airport_code, request.runways),
            "{runway_condition}": scenario_options.runway_condition,
            "{contamination_depth}": scenario_options.contamination_depth,
            "{bleed_status}": scenario_options.bleed_status,
            "{anti_icing}": scenario_options.anti_icing,
            "{temperature_range}": request.temperature_range or aircraft.default_temperature_range,
            "{wind_range}": request.wind_range or aircraft.default_wind_range,
            "{qnh_ref}": qnh_ref,
            "{qnh_ref_description}": f"QNHREF = {qnh_ref}" if request.describe_qnh_ref else "",
            "{derated}": scenario_options.derated,
            "{derate_value}": scenario_options.derated,
            "{thrust_label}": thrust_option.thrust_label,
        }

        content = template
        for placeholder, value in replacements.items():
            content = content.replace(placeholder, value)

        unresolved = sorted(set(PLACEHOLDER_PATTERN.findall(content)))
        if unresolved:
            raise ValueError(f"Unresolved template placeholders: {', '.join(unresolved)}")

        return content

    def _build_airport_runway(self, airport_code: str, runways: tuple[str, ...]) -> str:
        airport = airport_code.strip().upper()
        if not runways:
            return f"{airport}/*"

        return ",".join(f"{airport}/{runway.strip().upper()}" for runway in runways)
