"""Validation rules for performance calculation requests."""

from __future__ import annotations

import re

from stas_app.models.request import PerformanceRequest
from stas_app.models.runway import RunwayDataset
from stas_app.services.aircraft_registry import AircraftRegistry
from stas_app.utils.aviation_date import validate_aviation_date


NUMBER_PATTERN = re.compile(r"^-?\d+(?:\.\d+)?$")


class ValidationError(ValueError):
    """Raised when user input cannot be used for a STAS calculation."""


def validate_performance_request(
    request: PerformanceRequest,
    aircraft_registry: AircraftRegistry,
    runway_dataset: RunwayDataset,
) -> PerformanceRequest:
    """Validate a user request before building STAS input."""

    _validate_aircraft(request, aircraft_registry)
    _validate_airport_and_runways(request, runway_dataset)
    _validate_temperature_range(request.temperature_range)
    _validate_wind_range(request.wind_range)
    _validate_qnh(request.qnh_ref)
    _validate_report_date_override(request.report_date_override)
    return request


def _validate_aircraft(request: PerformanceRequest, aircraft_registry: AircraftRegistry) -> None:
    if not request.aircraft_code.strip():
        raise ValidationError("Aircraft must be selected")

    try:
        aircraft = aircraft_registry.get(request.aircraft_code)
    except KeyError as exc:
        raise ValidationError(f"Unsupported aircraft: {request.aircraft_code}") from exc

    try:
        aircraft.get_thrust_option(request.thrust_option)
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc


def _validate_airport_and_runways(request: PerformanceRequest, runway_dataset: RunwayDataset) -> None:
    airport_code = request.airport_code.strip().upper()
    if not airport_code:
        raise ValidationError("Airport must be selected")

    if not runway_dataset.airport_exists(airport_code):
        raise ValidationError(f"Airport does not exist in runway data: {airport_code}")

    allowed_runways = set(runway_dataset.get_runway_ids(airport_code))
    for runway in request.runways:
        normalized_runway = runway.strip().upper()
        if normalized_runway not in allowed_runways:
            raise ValidationError(f"Runway {normalized_runway} does not belong to airport {airport_code}")


def _validate_temperature_range(value: str) -> None:
    if not value:
        return

    for item in value.split(","):
        token = item.strip()
        if not token:
            raise ValidationError("Temperature range contains an empty item")

        parts = token.split(":")
        if len(parts) == 1:
            _parse_number(parts[0], "temperature")
            continue

        if len(parts) != 3:
            raise ValidationError(f"Invalid temperature range item: {token}")

        start = _parse_number(parts[0], "temperature")
        end = _parse_number(parts[1], "temperature")
        step = _parse_number(parts[2], "temperature step")
        if step <= 0:
            raise ValidationError(f"Temperature step must be positive: {token}")
        if start == end:
            raise ValidationError(f"Temperature range start and end cannot be equal: {token}")


def _validate_wind_range(value: str) -> None:
    if not value:
        return

    for item in value.split(","):
        token = item.strip()
        if not token:
            raise ValidationError("Wind range contains an empty item")
        _parse_number(token, "wind")


def _validate_qnh(value: str) -> None:
    if not value:
        return

    qnh = _parse_number(value, "QNH")
    if qnh <= 0:
        raise ValidationError("QNH must be positive")


def _validate_report_date_override(value: str) -> None:
    if not value:
        return

    try:
        validate_aviation_date(value)
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc


def _parse_number(value: str, field_name: str) -> float:
    token = value.strip()
    if not NUMBER_PATTERN.match(token):
        raise ValidationError(f"Invalid {field_name} value: {value}")
    return float(token)
