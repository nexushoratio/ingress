"""Tests for routes.py"""

import unittest

from mundane import app

from ingress import routes


class MundaneCommandsTest(unittest.TestCase):

    def test_basic(self):
        my_app = app.ArgparseApp()
        my_app.safe_new_shared_parser('bookmarks')

        routes.mundane_commands(my_app)


class RouteTest(unittest.TestCase):

    def test_basic(self):
        self.assertTrue(routes.route)


if __name__ == '__main__':  # pragma: no cover
    unittest.main()
