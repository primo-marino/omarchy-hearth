#!/usr/bin/env python3
import unittest

import ha_bridge


class HaSessionStateTests(unittest.TestCase):
    def test_apply_state_updates_existing_and_adds_new(self):
        sess = ha_bridge.HaSession("home", "http://127.0.0.1:8123", False, "tok")
        first = {"entity_id": "sensor.solar_power", "state": "100", "attributes": {}}
        sess.last_states = [first]
        sess._state_index = {"sensor.solar_power": first}

        sess.apply_state({"entity_id": "sensor.solar_power", "state": "250", "attributes": {}})
        self.assertEqual(sess._state_index["sensor.solar_power"]["state"], "250")
        self.assertEqual(sess.last_states[0]["state"], "250")

        sess.apply_state({"entity_id": "sensor.grid_w", "state": "50", "attributes": {}})
        self.assertEqual(sess._state_index["sensor.grid_w"]["state"], "50")
        self.assertEqual(len(sess.last_states), 2)


if __name__ == "__main__":
    unittest.main()
