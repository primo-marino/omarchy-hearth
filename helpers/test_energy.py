#!/usr/bin/env python3
import unittest

import energy


NESTED_GRID = {
    "energy_sources": [
        {"type": "solar", "stat_energy_from": "sensor.solar_energy", "stat_rate": "sensor.solar_power"},
        {
            "type": "grid",
            "flow_from": [
                {"stat_energy_from": "sensor.grid_import_peak"},
                {"stat_energy_from": "sensor.grid_import_offpeak"},
            ],
            "flow_to": [{"stat_energy_to": "sensor.grid_export"}],
        },
        {"type": "battery", "stat_energy_from": "sensor.battery_out"},
    ]
}

FLAT_GRID = {
    "energy_sources": [
        {"type": "grid", "stat_energy_from": "sensor.grid_in", "stat_energy_to": "sensor.grid_out", "stat_power": "sensor.grid_w"},
    ]
}

SOLAR_ONLY = {
    "energy_sources": [
        {"type": "solar", "stat_energy_from": "sensor.solar_energy", "stat_power": "sensor.solar_power"},
    ]
}


class EnergyPrefsTests(unittest.TestCase):
    def test_nested_grid_and_solar(self):
        g = energy.parse_prefs(NESTED_GRID)
        self.assertEqual(g["solar"], ["sensor.solar_energy"])
        self.assertEqual(g["import"], ["sensor.grid_import_peak", "sensor.grid_import_offpeak"])
        self.assertEqual(g["export"], ["sensor.grid_export"])
        self.assertEqual(g["power"], ["sensor.solar_power"])
        self.assertNotIn("sensor.battery_out", g["solar"])

    def test_flat_grid(self):
        g = energy.parse_prefs(FLAT_GRID)
        self.assertEqual(g["import"], ["sensor.grid_in"])
        self.assertEqual(g["export"], ["sensor.grid_out"])
        self.assertEqual(g["power"], ["sensor.grid_w"])
        self.assertEqual(g["solar"], [])

    def test_solar_only(self):
        g = energy.parse_prefs(SOLAR_ONLY)
        self.assertEqual(g["solar"], ["sensor.solar_energy"])
        self.assertEqual(g["import"], [])
        self.assertEqual(g["power"], ["sensor.solar_power"])

    def test_empty_sources_hides(self):
        self.assertIsNone(energy.parse_prefs({"energy_sources": []}))
        self.assertIsNone(energy.parse_prefs({}))
        self.assertIsNone(energy.parse_prefs(None))

    def test_error_shaped_prefs_hide(self):
        self.assertIsNone(energy.parse_prefs("nope"))
        self.assertIsNone(energy.parse_prefs({"energy_sources": {"type": "solar"}}))

    def test_battery_only_hides(self):
        self.assertIsNone(energy.parse_prefs({"energy_sources": [{"type": "battery", "stat_energy_from": "x"}]}))

    def test_sum_changes_and_missing_column(self):
        result = {
            "sensor.solar_energy": [{"change": 12.4}, {"change": 0.1}],
            "sensor.grid_export": [{"change": 8.8}],
        }
        g = energy.parse_prefs(NESTED_GRID)
        self.assertAlmostEqual(energy.sum_changes(result, g["solar"]), 12.5)
        self.assertIsNone(energy.sum_changes(result, g["import"]))
        self.assertAlmostEqual(energy.sum_changes(result, g["export"]), 8.8)

    def test_pack_hides_when_all_columns_missing(self):
        g = energy.parse_prefs(SOLAR_ONLY)
        packed = energy.pack(g, {}, [])
        self.assertFalse(packed["enabled"])

    def test_live_power_first_numeric(self):
        states = [
            {"entity_id": "sensor.solar_power", "state": "unavailable"},
            {"entity_id": "sensor.grid_w", "state": "350.2"},
        ]
        self.assertAlmostEqual(energy.live_power_w(states, ["sensor.solar_power", "sensor.grid_w"]), 350.2)
        self.assertIsNone(energy.live_power_w(states, ["sensor.not_configured"]))

    def test_live_power_converts_kw(self):
        states = [{
            "entity_id": "sensor.solar_power",
            "state": "11.128",
            "attributes": {"unit_of_measurement": "kW"},
        }]
        self.assertAlmostEqual(energy.live_power_w(states, ["sensor.solar_power"]), 11128.0)

    def test_empty_nested_flows_still_read_flat_grid(self):
        prefs = {
            "energy_sources": [{
                "type": "grid",
                "flow_from": [],
                "flow_to": [],
                "stat_energy_from": "sensor.grid_in",
                "stat_energy_to": "sensor.grid_out",
            }]
        }
        g = energy.parse_prefs(prefs)
        self.assertEqual(g["import"], ["sensor.grid_in"])
        self.assertEqual(g["export"], ["sensor.grid_out"])

    def test_today_kwh_prefers_change_then_sum_delta(self):
        by_change = {"sensor.solar_energy": [{"change": 1.5}, {"change": 2.5}]}
        self.assertAlmostEqual(energy.today_kwh(by_change, ["sensor.solar_energy"]), 4.0)
        by_sum = {"sensor.solar_energy": [{"sum": 100.0}, {"sum": 143.4}]}
        self.assertAlmostEqual(energy.today_kwh(by_sum, ["sensor.solar_energy"]), 43.4)

    def test_mwh_without_units_would_look_like_zero_kwh(self):
        # Envoy lifetime production is MWh; 43 kWh today arrives as 0.043 without units.
        raw = {"sensor.solar_energy": [{"change": 0.043384}]}
        self.assertAlmostEqual(energy.today_kwh(raw, ["sensor.solar_energy"]), 0.043384)
        converted = {"sensor.solar_energy": [{"change": 43.384}]}
        self.assertAlmostEqual(energy.today_kwh(converted, ["sensor.solar_energy"]), 43.384)

    def test_stats_payload_asks_for_kwh(self):
        payload = energy.stats_payload("2026-09-12T00:00:00-04:00", ["sensor.solar_energy"])
        self.assertEqual(payload["units"], {"energy": "kWh"})
        self.assertEqual(payload["period"], "hour")
        self.assertIn("change", payload["types"])

    def test_dedupe_identical_stat_ids(self):
        prefs = {
            "energy_sources": [
                {"type": "solar", "stat_energy_from": "sensor.solar_energy"},
                {"type": "solar", "stat_energy_from": "sensor.solar_energy"},
            ]
        }
        self.assertEqual(energy.parse_prefs(prefs)["solar"], ["sensor.solar_energy"])


if __name__ == "__main__":
    unittest.main()
