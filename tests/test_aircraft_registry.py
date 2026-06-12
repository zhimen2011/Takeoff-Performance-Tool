from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
sys.path.insert(0, str(SRC_DIR))

from stas_app.services.aircraft_registry import AircraftRegistry


class AircraftRegistryTests(unittest.TestCase):
    def test_loads_only_currently_supported_aircraft(self) -> None:
        registry = AircraftRegistry.from_directory(ROOT_DIR / "config" / "aircraft")

        self.assertEqual(registry.supported_codes(), ("738", "777F"))

    def test_loads_777f_thrust_options(self) -> None:
        registry = AircraftRegistry.from_directory(ROOT_DIR / "config" / "aircraft")
        aircraft = registry.get("777F")

        self.assertTrue(aircraft.supports_thrust_options)
        self.assertEqual([option.label for option in aircraft.thrust_options], ["正常", "减推力10%", "减推力20%", "1L1BUMP"])


if __name__ == "__main__":
    unittest.main()

