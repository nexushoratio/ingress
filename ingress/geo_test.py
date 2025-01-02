"""Tests for geo.py"""

# pylint: disable=protected-access

import unittest

from mundane import app

from ingress import geo


class MundaneCommandsTest(unittest.TestCase):

    def test_basic(self):
        my_app = app.ArgparseApp()
        my_app.safe_new_shared_parser('bookmarks')
        my_app.safe_new_shared_parser('drawtools')
        my_app.safe_new_shared_parser('file')
        my_app.safe_new_shared_parser('folder_id_req_list')

        geo.mundane_commands(my_app)


class NeverCallTest(unittest.TestCase):

    def test_geo(self):
        with self.assertRaises(geo.Error):
            geo._geo(None)


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
