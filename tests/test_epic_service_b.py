import unittest

VALUE_B = 37


class ServiceBTests(unittest.TestCase):
    def test_b(self):
        self.assertEqual(VALUE_B, 37)
