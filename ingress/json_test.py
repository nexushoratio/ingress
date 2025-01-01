"""Tests for json.py"""

import unittest

from ingress import json


class MundaneSharedFlagsTest(unittest.TestCase):

    def test_basic(self):
        self.assertTrue(json.mundane_shared_flags)


class MundaneCommandsTest(unittest.TestCase):

    def test_basic(self):
        self.assertTrue(json.mundane_commands)


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
