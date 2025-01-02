"""Tests for addresses.py"""

# pylint: disable=protected-access

import unittest

from mundane import app

from ingress import addresses


class MundaneCommandsTest(unittest.TestCase):

    def test_basic(self):
        my_app = app.ArgparseApp()
        my_app.safe_new_shared_parser('bookmarks')
        my_app.safe_new_shared_parser('bookmark_label')

        addresses.mundane_commands(my_app)


class NeverCallTest(unittest.TestCase):

    def test_address(self):
        with self.assertRaises(addresses.Error):
            addresses._address(None)

    def test_type(self):
        with self.assertRaises(addresses.Error):
            addresses._type(None)

    def test_value(self):
        with self.assertRaises(addresses.Error):
            addresses._value(None)


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
