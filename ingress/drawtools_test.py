"""Tests for drawtools.py"""

import json
import tempfile
import unittest

from ingress import drawtools

TETRAHELIX = {
    'color': '#c3574a',
    'latLng': {
        'lat': 37.421963,
        'lng': -122.085126
    },
    'type': 'marker'
}

GOOGLE_VOLLEYBALL_SAND_COURT = {
    'COLOR': '#c3574a',
    'latLng': {
        'lat': 37.423521,
        'lng': -122.089649
    },
    'type': 'broken'
}


def save_to_temp_json(obj) -> str:
    """Save test data to a tempfile as JSON."""
    with tempfile.NamedTemporaryFile(mode='w', delete=False) as handle:
        json.dump(obj, handle)
    return handle.name


class LoadPointTest(unittest.TestCase):

    def test_happy_path(self):
        filename = save_to_temp_json([TETRAHELIX])
        point = drawtools.load_point(filename)

        self.assertEqual(str(point), 'POINT(-122.085126 37.421963)')

    def test_too_few(self):
        filename = save_to_temp_json([])
        with self.assertRaisesRegex(
                RuntimeError, 'should have one element; has 0 elements'):
            drawtools.load_point(filename)

    def test_too_many(self):
        filename = save_to_temp_json(
            [TETRAHELIX, GOOGLE_VOLLEYBALL_SAND_COURT])
        with self.assertRaisesRegex(
                RuntimeError, 'should have one element; has 2 elements'):
            drawtools.load_point(filename)

    def test_unknown_type(self):
        filename = save_to_temp_json([GOOGLE_VOLLEYBALL_SAND_COURT])
        with self.assertRaisesRegex(TypeError,
                                    '"broken" is a type not yet handled'):
            drawtools.load_point(filename)

    def test_empty_file(self):
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as handle:
            filename = handle.name
        with self.assertRaises(json.decoder.JSONDecodeError):
            drawtools.load_point(filename)

    def test_bad_json(self):
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as handle:
            handle.write('xyzzy')
            filename = handle.name
        with self.assertRaises(json.decoder.JSONDecodeError):
            drawtools.load_point(filename)

    def test_missing_file(self):
        with self.assertRaises(FileNotFoundError):
            drawtools.load_point('bogus')


if __name__ == '__main__':  # pragma: no cover
    unittest.main()
