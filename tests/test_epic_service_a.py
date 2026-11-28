import unittest

VALUE_A = 19


class ServiceATests(unittest.TestCase):
    def test_a(self):
        self.assertEqual(VALUE_A, 19)
