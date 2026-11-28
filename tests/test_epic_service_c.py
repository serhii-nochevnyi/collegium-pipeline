import unittest

from test_epic_service_a import VALUE_A
from test_epic_service_b import VALUE_B


class ServiceCTests(unittest.TestCase):
    def test_combined(self):
        self.assertEqual(VALUE_A + VALUE_B, 56)
