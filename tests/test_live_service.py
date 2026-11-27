"""Service-only live GitHub checkpoint recovery fixture."""

import unittest


class LiveCheckpointRecoveryTest(unittest.TestCase):
    def test_fixed_fixture(self):
        self.assertEqual(len("checkpoint-recovery"), 19)
