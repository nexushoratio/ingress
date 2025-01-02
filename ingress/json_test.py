"""Tests for json.py"""

import unittest

from mundane import app

from ingress import json


class MundaneSharedFlagsTest(unittest.TestCase):

    def test_basic(self):
        my_app = app.ArgparseApp()
        json.mundane_shared_flags(my_app)

        self.assertIsNotNone(my_app.get_shared_parser('file'))


class MundaneCommandsTest(unittest.TestCase):

    def test_basic(self):
        my_app = app.ArgparseApp()
        my_app.safe_new_shared_parser('file')

        json.mundane_commands(my_app)


class LoadTest(unittest.TestCase):

    def test_basic(self):
        self.assertTrue(json.load)


class SaveTest(unittest.TestCase):

    def test_basic(self):
        self.assertTrue(json.save)


class CleanTest(unittest.TestCase):

    def test_basic(self):
        self.assertTrue(json.clean)


class SaveBySizeTest(unittest.TestCase):

    def test_basic(self):
        self.assertTrue(json.save_by_size)


if __name__ == '__main__':  # pragma: no cover
    unittest.main()
