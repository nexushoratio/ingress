"""Tests for geo.py"""

import unittest

from ingress import geo


class MundaneCommandsTest(unittest.TestCase):

    def test_basic(self):
        self.assertTrue(geo.mundane_commands)


class BoundsTest(unittest.TestCase):

    def test_basic(self):
        self.assertTrue(geo.bounds)


class TrimTest(unittest.TestCase):

    def test_basic(self):
        self.assertTrue(geo.trim)


class DonutsTest(unittest.TestCase):

    def test_basic(self):
        self.assertTrue(geo.donuts)


class EllipseTest(unittest.TestCase):

    def test_basic(self):
        self.assertTrue(geo.ellipse)


class UpdateTest(unittest.TestCase):

    def test_basic(self):
        self.assertTrue(geo.update)


class ClusterTest(unittest.TestCase):

    def test_basic(self):
        self.assertTrue(geo.cluster)


if __name__ == '__main__':  # pragma: no cover
    unittest.main()
