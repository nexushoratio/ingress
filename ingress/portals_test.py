"""Tests for portals.py"""

# pylint: disable=protected-access

import unittest

from mundane import app

from ingress import portals


class MundaneCommandsTest(unittest.TestCase):

    def test_basic(self):
        my_app = app.ArgparseApp()
        my_app.safe_new_shared_parser('bookmarks')
        my_app.safe_new_shared_parser('bookmark_label')

        portals.mundane_commands(my_app)


class NeverCallTest(unittest.TestCase):

    def test_portal(self):
        with self.assertRaises(portals.Error):
            portals._portal(None)


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
