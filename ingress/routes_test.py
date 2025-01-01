"""Tests for routes.py"""

import unittest

from ingress import routes


class MundaneCommandsTest(unittest.TestCase):

    def test_basic(self):
        self.assertTrue(routes.mundane_commands)


class RouteTest(unittest.TestCase):

    def test_basic(self):
        self.assertTrue(routes.route)


if __name__ == '__main__':  # pragma: no cover
    unittest.main()
