"""Aircraft configuration models."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ThrustOption:
    """One selectable thrust option for an aircraft."""

    label: str
    derated: str = "0"
    thrust_label: str = ""


@dataclass(frozen=True)
class AircraftConfig:
    """Configuration that drives aircraft-specific STAS input generation."""

    code: str
    display_name: str
    template: str
    default_temperature_range: str
    default_wind_range: str
    default_qnh: str = "1013.25"
    supports_thrust_options: bool = False
    thrust_options: tuple[ThrustOption, ...] = ()

    def get_thrust_option(self, label: str | None) -> ThrustOption:
        if not self.supports_thrust_options:
            if label:
                raise ValueError(f"Aircraft {self.code} does not support thrust option: {label}")
            return ThrustOption(label="", derated="0", thrust_label="")

        if not self.thrust_options:
            raise ValueError(f"Aircraft {self.code} is missing thrust options")

        if not label:
            return self.thrust_options[0]

        for option in self.thrust_options:
            if option.label == label:
                return option

        raise ValueError(f"Unknown thrust option for aircraft {self.code}: {label}")

