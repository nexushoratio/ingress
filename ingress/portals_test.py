"""Tests for portals.py"""

import unittest

from ingress import portals


class MundaneCommandsTest(unittest.TestCase):

    def test_basic(self):
        self.assertTrue(portals.mundane_commands)


class IngestTest(unittest.TestCase):

    def test_basic(self):
        self.assertTrue(portals.ingest)


class ExpungeTest(unittest.TestCase):

    def test_basic(self):
        self.assertTrue(portals.expunge)


class ExportTest(unittest.TestCase):

    def test_basic(self):
        self.assertTrue(portals.export)


class ShowTest(unittest.TestCase):

    def test_basic(self):
        self.assertTrue(portals.show)


if __name__ == '__main__':  # pragma: no cover
    unittest.main()
