"""Helper functions for writing tests."""

from __future__ import annotations

import dataclasses
import inspect
import logging
import sys
import tempfile
import typing
from unittest import mock

from ingress import database

if typing.TYPE_CHECKING:  # pragma: no cover
    import types
    import unittest


@dataclasses.dataclass(kw_only=True, frozen=True)
class MockedImports:
    """Original and mocked modules keyed by module name."""
    modules: dict[str, typing.Any]
    mocks: dict[str, typing.Any]


class NotConfiguredError(Exception):
    pass


def mock_ingress_imports(
    test: unittest.TestCase, mut: types.ModuleType
) -> MockedImports:
    """Mock out and disable almost all 'ingress' imports by default.

    Certain items, such as the ORM definitions, regularly need to stick
    around.

    Test methods must reenable individual functions on demand.
    """
    mocked_imports = MockedImports(modules=dict(), mocks=dict())
    # Save before it gets mocked out
    base = database.Base
    for name, mod in inspect.getmembers(mut, inspect.ismodule):
        if mod.__spec__.name.startswith('ingress.'):
            patcher = mock.patch.object(mut, name, autospec=True)
            original, _ = patcher.get_original()
            mock_ = patcher.start()
            test.addCleanup(patcher.stop)
            for attr_name in dir(mock_):
                attr_item = getattr(mock_, attr_name)
                if isinstance(attr_item, mock.MagicMock):
                    attr_item.side_effect = NotConfiguredError
                try:
                    orig_item = getattr(original, attr_name)
                    if inspect.isclass(orig_item) and issubclass(orig_item,
                                                                 base):
                        setattr(mock_, attr_name, orig_item)
                except AttributeError:
                    pass

            mocked_imports.modules[name] = original
            mocked_imports.mocks[name] = mock_

    return mocked_imports


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
