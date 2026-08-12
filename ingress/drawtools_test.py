"""Tests for drawtools.py"""

# pylint: disable=protected-access

import json
import tempfile
import unittest

from mundane import app

from ingress import drawtools

TETRAHELIX = {
    'color': '#c3574a',
    'latLng': {
        'lat': 37.421963,
        'lng': -122.085126
    },
    'type': 'marker'
}

CUPIDS_SPAN = {
    'color': 'orange',
    'latLng': {
        'lat': 37.791541,
        'lng': -122.390014
    },
    'type': 'circle',
    'radius': 1000
}

GOOGLE_VOLLEYBALL_SAND_COURT = {
    'color': '#c3574a',
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


class MundaneSharedFlagsTest(unittest.TestCase):

    def test_basic(self):
        my_app = app.ArgparseApp()
        drawtools.mundane_shared_flags(my_app)

        self.assertIsNotNone(my_app.get_shared_parser('drawtools'))


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
        filename = save_to_temp_json([TETRAHELIX, CUPIDS_SPAN])
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


class LoadPointsTest(unittest.TestCase):

    def test_single_item(self):
        filename = save_to_temp_json([TETRAHELIX])
        points = drawtools.load_points(filename)

        self.assertEqual(len(points), 1)
        point = list(points)[0]
        self.assertEqual(str(point), 'POINT(-122.085126 37.421963)')

    def test_zero_items(self):
        filename = save_to_temp_json([])
        points = drawtools.load_points(filename)

        self.assertEqual(len(points), 0)

    def test_multiple_items(self):
        filename = save_to_temp_json([TETRAHELIX, CUPIDS_SPAN])
        points = drawtools.load_points(filename)

        self.assertEqual(len(points), 2)

    def test_unknown_type(self):
        filename = save_to_temp_json(
            [CUPIDS_SPAN, GOOGLE_VOLLEYBALL_SAND_COURT]
        )
        with self.assertRaisesRegex(TypeError,
                                    '"broken" is a type not yet handled'):
            drawtools.load_points(filename)

    def test_empty_file(self):
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as handle:
            filename = handle.name
        with self.assertRaises(json.decoder.JSONDecodeError):
            drawtools.load_points(filename)

    def test_bad_json(self):
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as handle:
            handle.write('xyzzy')
            filename = handle.name
        with self.assertRaises(json.decoder.JSONDecodeError):
            drawtools.load_points(filename)

    def test_missing_file(self):
        with self.assertRaises(FileNotFoundError):
            drawtools.load_points('bogus')


class RainbowTest(unittest.TestCase):

    def test_red(self):
        self.assertEqual(drawtools._rainbow(0.0), '#ff0000')

    def test_orangish(self):
        self.assertEqual(drawtools._rainbow(0.1), '#ff8000')

    def test_yellow(self):
        self.assertEqual(drawtools._rainbow(0.2), '#ffff00')

    def test_chartreuse(self):
        self.assertEqual(drawtools._rainbow(0.3), '#80ff00')

    def test_green(self):
        self.assertEqual(drawtools._rainbow(0.4), '#00ff00')

    def test_spring_green(self):
        self.assertEqual(drawtools._rainbow(0.5), '#00ff80')

    def test_cyan(self):
        self.assertEqual(drawtools._rainbow(0.6), '#00ffff')

    def test_dodger_bluish(self):
        self.assertEqual(drawtools._rainbow(0.7), '#0080ff')

    def test_blue(self):
        self.assertEqual(drawtools._rainbow(0.8), '#0000ff')

    def test_purplish(self):
        self.assertEqual(drawtools._rainbow(0.9), '#8000ff')

    def test_magenta(self):
        self.assertEqual(drawtools._rainbow(1.0), '#ff00ff')

    def test_too_low(self):
        with self.assertRaisesRegex(drawtools.Error, 'out of range: -0.01'):
            drawtools._rainbow(-0.01)

    def test_too_high(self):
        with self.assertRaisesRegex(drawtools.Error, 'out of range: 1.02'):
            drawtools._rainbow(1.02)


if __name__ == '__main__':  # pragma: no cover
    unittest.main()
