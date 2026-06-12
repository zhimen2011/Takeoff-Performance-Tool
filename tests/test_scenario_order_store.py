from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
sys.path.insert(0, str(SRC_DIR))

from stas_app.storage.scenario_order_store import ScenarioOrderStore


class ScenarioOrderStoreTests(unittest.TestCase):
    def test_save_load_and_delete_order(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ScenarioOrderStore(Path(temp_dir) / "scenario_orders.json")

            store.save_order(
                "dry_derate",
                [
                    {
                        "runway_condition": "DRY",
                        "contamination_depth": "",
                        "thrust_option": "减推力20%",
                        "derate": "20",
                        "bleed": "ON",
                        "anti_icing": "0",
                        "temperature_range": "45:31:1",
                        "wind_range": "-5,0,15",
                        "qnh_ref": "1008",
                        "describe_qnh_ref": "false",
                        "aircraft_code": "SHOULD_NOT_SAVE",
                        "airport_code": "SHOULD_NOT_SAVE",
                        "runways": "SHOULD_NOT_SAVE",
                        "manual_report_template_id": "SHOULD_NOT_SAVE",
                    }
                ],
            )

            self.assertEqual(
                store.load_all(),
                {
                    "dry_derate": [
                        {
                            "runway_condition": "DRY",
                            "contamination_depth": "",
                            "thrust_option": "减推力20%",
                            "derate": "20",
                            "bleed": "ON",
                            "anti_icing": "0",
                            "temperature_range": "45:31:1",
                            "wind_range": "-5,0,15",
                            "qnh_ref": "1008",
                            "describe_qnh_ref": "false",
                        }
                    ]
                },
            )

            store.delete_order("dry_derate")

            self.assertEqual(store.load_all(), {})

    def test_load_legacy_order_does_not_invent_blank_queue_conditions(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "scenario_orders.json"
            path.write_text(
                """
{
  "legacy": [
    {
      "runway_condition": "DRY",
      "contamination_depth": "",
      "thrust_option": "正常",
      "derate": "",
      "bleed": "ON",
      "anti_icing": "0"
    }
  ]
}
""".strip(),
                encoding="utf-8",
            )

            self.assertEqual(
                ScenarioOrderStore(path).load_all()["legacy"][0],
                {
                    "runway_condition": "DRY",
                    "contamination_depth": "",
                    "thrust_option": "正常",
                    "derate": "",
                    "bleed": "ON",
                    "anti_icing": "0",
                },
            )


if __name__ == "__main__":
    unittest.main()
