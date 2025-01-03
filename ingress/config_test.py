"""Tests for config.py"""

# pylint: disable=protected-access

import unittest

from mundane import app

from ingress import config


class MundaneCommandsTest(unittest.TestCase):

    def test_basic(self):
        my_app = app.ArgparseApp()

        config.mundane_commands(my_app)


class NeverCallTest(unittest.TestCase):

    def test_config(self):
        with self.assertRaises(config.Error):
            config._config(None)

    def test_format(self):
        with self.assertRaises(config.Error):
            config._format(None)

    def test_format_command(self):
        with self.assertRaises(config.Error):
            config._format_command(None)


if __name__ == '__main__':  # pragma: no cover
    unittest.main()
