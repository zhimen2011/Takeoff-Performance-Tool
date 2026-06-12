"""Load and expose aircraft configuration files."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Iterable

from stas_app.models.aircraft import AircraftConfig, ThrustOption


class AircraftRegistry:
    """Registry for aircraft supported by the new application."""

    def __init__(self, aircraft: Iterable[AircraftConfig]) -> None:
        self._aircraft = {item.code: item for item in aircraft}

    @classmethod
    def from_directory(cls, directory: str | Path) -> "AircraftRegistry":
        config_dir = Path(directory)
        if not config_dir.exists():
            raise FileNotFoundError(f"Aircraft config directory does not exist: {config_dir}")

        aircraft = []
        for config_path in sorted(config_dir.glob("*.toml")):
            aircraft.append(cls._load_config(config_path))

        if not aircraft:
            raise ValueError(f"No aircraft config files found in: {config_dir}")

        return cls(aircraft)

    @staticmethod
    def _load_config(config_path: Path) -> AircraftConfig:
        with config_path.open("rb") as file:
            data = tomllib.load(file)

        thrust_options = tuple(
            ThrustOption(
                label=str(option.get("label", "")),
                derated=str(option.get("derated", "0")),
                thrust_label=str(option.get("thrust_label", "")),
            )
            for option in data.get("thrust_options", [])
        )

        return AircraftConfig(
            code=str(data["code"]),
            display_name=str(data.get("display_name", data["code"])),
            template=str(data["template"]),
            default_temperature_range=str(data["default_temperature_range"]),
            default_wind_range=str(data["default_wind_range"]),
            default_qnh=str(data.get("default_qnh", "1013.25")),
            supports_thrust_options=bool(data.get("supports_thrust_options", False)),
            thrust_options=thrust_options,
        )

    def supported_codes(self) -> tuple[str, ...]:
        return tuple(sorted(self._aircraft))

    def get(self, aircraft_code: str) -> AircraftConfig:
        code = aircraft_code.strip().upper()
        try:
            return self._aircraft[code]
        except KeyError as exc:
            raise KeyError(f"Unsupported aircraft: {aircraft_code}") from exc

