"""Helper functions for writing tests."""

from __future__ import annotations

import tempfile
import typing

from ingress import database

if typing.TYPE_CHECKING:  # pragma: no cover
    import unittest


def database_connection(test: unittest.TestCase) -> database.Database:
    """Create a database in temporary directory."""
    return database.Database(tempfile.mkdtemp(), test.id())
