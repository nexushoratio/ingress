"""Tests for test_helper.py"""

import types
import unittest
from unittest import mock

from ingress import test_helper


class MockAllImportsTest(unittest.TestCase):

    def setUp(self):
        self._mocks = test_helper.mock_ingress_imports(self, test_helper)

    def test_not_configured(self):
        with self.assertRaises(test_helper.NotConfiguredError):
            test_helper.database.mundane_global_flags(None)

    def test_allow_call_directly(self):
        test_helper.database.mundane_global_flags.side_effect = None
        test_helper.database.mundane_global_flags(None)

    def test_allow_call_via_mocks(self):
        self._mocks.mocks['database'].mundane_global_flags.side_effect = None
        test_helper.database.mundane_global_flags(None)

    def test_only_ingress_mocked(self):
        # is mocked
        self.assertIsInstance(test_helper.database, mock.Base)
        self.assertIsInstance(
            test_helper.database.mundane_global_flags, mock.Base
        )

        # is not mocked
        self.assertIsInstance(test_helper.mock, types.ModuleType)
        self.assertIsInstance(test_helper.mock.patch, types.FunctionType)


class DatabaseConnectionTest(unittest.TestCase):

    def test_creation(self):
        dbc = test_helper.database_connection(self)
        self.assertIsInstance(dbc, test_helper.database.Database)


if __name__ == '__main__':  # pragma: no cover
    unittest.main()
