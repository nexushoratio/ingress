"""Helper functions for writing tests."""

from __future__ import annotations

import logging
import sys
import tempfile
import typing

from ingress import database

if typing.TYPE_CHECKING:  # pragma: no cover
    import unittest


def prep_sys_argv(test: unittest.TestCase):
    """Set sys.argv to something knowable to assist testing."""
    orig_sys_argv = sys.argv

    def restore_sys_argv():
        sys.argv = orig_sys_argv

    test.addCleanup(restore_sys_argv)

    test.maxDiff = None


def prep_logger_handlers(test: unittest.TestCase):
    """Restore known logging handlers after each test."""
    root_logger = logging.getLogger()
    orig_handlers = root_logger.handlers.copy()

    def restore_orig_handlers():
        for hdlr in root_logger.handlers:
            if hdlr not in orig_handlers:
                root_logger.removeHandler(hdlr)
                hdlr.close()
        for hdlr in orig_handlers:
            if hdlr not in root_logger.handlers:
                root_logger.addHandler(hdlr)

    test.addCleanup(restore_orig_handlers)


def database_connection(test: unittest.TestCase) -> database.Database:
    """Create a database in temporary directory."""
    dbc = database.Database(tempfile.mkdtemp(), test.id())
    test.addCleanup(dbc.dispose)
    return dbc
