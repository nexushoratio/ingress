"""Tests for database.py"""

import unittest

from ingress import database


# pylint: disable=protected-access
class ConversionsTest(unittest.TestCase):

    def test_latlng_via_point(self):
        tetrahelix = '37.423521,-122.089649'

        result = database._point_to_latlng(
            database._latlng_to_point(tetrahelix))

        self.assertEqual(tetrahelix, result)

    def test_latlng_dict_via_point(self):
        tetrahelix = '37.423521,-122.089649'
        # E.g., as seen in drawtool
        latlng = {
            "lat": 37.423521,
            "lng": -122.089649,
        }

        result = database._point_to_latlng(
            database.latlng_dict_to_point(latlng))

        self.assertEqual(tetrahelix, result)


if __name__ == '__main__':  # pragma: no cover
    unittest.main()
