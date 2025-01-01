"""Tests for google.py"""

import unittest

from ingress import google


class DirectionsTest(unittest.TestCase):

    def test_basic(self):
        self.assertTrue(google.directions)


class LatlngToAddressTest(unittest.TestCase):

    def test_basic(self):
        self.assertTrue(google.latlng_to_address)


class EncodePolylineTest(unittest.TestCase):

    def test_basic(self):
        self.assertTrue(google.encode_polyline)


class DecodePolylineTest(unittest.TestCase):

    def test_basic(self):
        self.assertTrue(google.decode_polyline)


if __name__ == '__main__':  # pragma: no cover
    unittest.main()
