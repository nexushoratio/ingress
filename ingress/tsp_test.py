"""Tests for tsp.py"""

import unittest

from ingress import tsp


class OptimizeTest(unittest.TestCase):

    def test_basic(self):
        self.assertTrue(tsp.optimize)


if __name__ == '__main__':  # pragma: no cover
    unittest.main()
