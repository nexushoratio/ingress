"""Tests for main.py"""

import contextlib
import io
import os
import sys
import unittest

from ingress import __main__
from ingress import test_helper


class MainTest(unittest.TestCase):

    def setUp(self):
        test_helper.prep_sys_argv(self)
        test_helper.prep_logger_handlers(self)

    def test_main(self):
        sys.argv = [self.id()]

        stdout = io.StringIO()
        stderr = io.StringIO()
        with self.assertRaises(
                SystemExit) as result, contextlib.redirect_stdout(
                    stdout), contextlib.redirect_stderr(stderr):
            __main__.main()

        self.assertIn(
            'Perform a number of Ingress related functions.',
            stdout.getvalue()
        )
        self.assertEqual(stderr.getvalue(), '')
        self.assertEqual(result.exception.code, os.EX_USAGE)


if __name__ == '__main__':  # pragma: no cover
    unittest.main()
