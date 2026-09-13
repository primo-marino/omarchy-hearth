#!/usr/bin/env python3
"""HA maps percentage → speed with math.ceil(percentage / step)."""
import math
import unittest


def ha_speed(percentage, n=3):
    step = 100.0 / n
    return int(math.ceil(percentage / step - 1e-9))


def hearth_pct(idx, n=3):
    if idx <= 0:
        return 0
    if idx >= n:
        return 100
    return (idx * 100) // n


def buggy_pct(idx, n=3):
    if idx <= 0:
        return 0
    if idx >= n:
        return 100
    return int(round(idx * (100.0 / n)))


class FanMathTests(unittest.TestCase):
    def test_speed_2_must_not_ceil_to_high(self):
        self.assertEqual(ha_speed(67, 3), 3)
        self.assertEqual(buggy_pct(2, 3), 67)
        self.assertEqual(hearth_pct(2, 3), 66)
        self.assertEqual(ha_speed(hearth_pct(2, 3), 3), 2)

    def test_all_three_speeds_round_trip(self):
        for n in (3, 4, 5):
            for i in range(1, n + 1):
                self.assertEqual(ha_speed(hearth_pct(i, n), n), i, "n=%s i=%s" % (n, i))


if __name__ == "__main__":
    unittest.main()
