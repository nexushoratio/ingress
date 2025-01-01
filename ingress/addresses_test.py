"""Tests for addresses.py"""

import unittest

from ingress import addresses


class MundaneCommandsTest(unittest.TestCase):

    def test_basic(self):
        self.assertTrue(addresses.mundane_commands)


class UpdateTest(unittest.TestCase):

    def test_basic(self):
        self.assertTrue(addresses.update)


class TypeListTest(unittest.TestCase):

    def test_basic(self):
        self.assertTrue(addresses.type_list)


class TypeSetTest(unittest.TestCase):

    def test_basic(self):
        self.assertTrue(addresses.type_set)


class TypeDelTest(unittest.TestCase):

    def test_basic(self):
        self.assertTrue(addresses.type_del)


class ValueListTest(unittest.TestCase):

    def test_basic(self):
        self.assertTrue(addresses.value_list)


class ValueSetTest(unittest.TestCase):

    def test_basic(self):
        self.assertTrue(addresses.value_set)


class ValueDelTest(unittest.TestCase):

    def test_basic(self):
        self.assertTrue(addresses.value_del)


class PruneTest(unittest.TestCase):

    def test_basic(self):
        self.assertTrue(addresses.prune)


if __name__ == '__main__':  # pragma: no cover
    unittest.main()
