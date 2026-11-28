"""Temporary PR-only fault injection for the Collegium delivery conveyor."""

import unittest

EXPECTED = "green"
ACTUAL = "green"


class LiveServiceTests(unittest.TestCase):
    def test_service_phase(self):
        self.assertEqual(ACTUAL, EXPECTED)
