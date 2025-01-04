"""Tests for test_helper.py"""

import unittest

from ingress import test_helper


class DatabaseConnectionTest(unittest.TestCase):

    def test_creation(self):
        dbc = test_helper.database_connection(self)
        self.assertIsInstance(dbc, test_helper.database.Database)


if __name__ == '__main__':  # pragma: no cover
    unittest.main()
