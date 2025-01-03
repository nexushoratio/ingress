"""Commands for tool configuration."""

from __future__ import annotations

import typing

from ingress import database

if typing.TYPE_CHECKING:  # pragma: no cover
    import argparse

    from mundane import app

sqla = database.sqlalchemy


class Error(Exception):
    """Base module exception."""


def mundane_commands(ctx: app.ArgparseApp):
    """Parser registration API."""

    config_cmds = ctx.new_subparser(
        ctx.register_command(_config, name='config', usage_only=True)
    )

    format_cmds = ctx.new_subparser(
        ctx.register_command(
            _format, name='format', usage_only=True, subparser=config_cmds
        )
    )

    fmt_cmd_cmds = ctx.new_subparser(
        ctx.register_command(
            _format_command,
            name='command',
            usage_only=True,
            subparser=format_cmds
        )
    )

    ctx.register_command(_format_list, name='list', subparser=format_cmds)
    ctx.register_command(_format_add, name='add', subparser=format_cmds)
    ctx.register_command(_format_del, name='del', subparser=format_cmds)
    ctx.register_command(_format_init, name='init', subparser=format_cmds)

    ctx.register_command(_fmt_cmd_list, name='list', subparser=fmt_cmd_cmds)
    ctx.register_command(_fmt_cmd_add, name='add', subparser=fmt_cmd_cmds)
    ctx.register_command(_fmt_cmd_del, name='del', subparser=fmt_cmd_cmds)


def _config(args: argparse.Namespace) -> int:
    """(V) A family of configuration commands."""
    raise Error('This function should never be called.')


def _format(args: argparse.Namespace) -> int:
    """(V) A family of commands for configuring predefined formatting strings.

    Some commands support a formatting style used in the Python programming
    language known as "PEP 3103".  For this tool, that generally means that
    fields will listed as "{field-name}".

    Named formatting strings can be defined so that they can be easily be
    selected.  The tool can register some predefined examples as starting
    points.

    Commands that support formatting will take the "-f|--format" flag, and
    named formats can be selected by surrounding them with the colon (:)
    character.  The special format "=list=" will list formats registered for a
    given command, and "-L|--list-fields" will list the fields that command
    supports.

    Each command that supports formatting can be assigned a default format.

    Hint: Current only "portal show" supports formatting.
    """
    raise Error('This function should never be called.')


def _format_command(args: argparse.Namespace) -> int:
    """(V) Commands for associating formatting strings to commands."""
    raise Error('This function should never be called.')


def _format_list(args: argparse.Namespace) -> int:
    """(V) List the known named formatting strings."""
    print(f'{args.name}: TBD')

    return 0


def _format_add(args: argparse.Namespace) -> int:
    """(V) Add a named formatting strings."""
    print(f'{args.name}: TBD')

    return 0


def _format_del(args: argparse.Namespace) -> int:
    """(V) Delete named formatting strings."""
    print(f'{args.name}: TBD')

    return 0


def _format_init(args: argparse.Namespace) -> int:
    """(V) Initialize named formatting strings."""
    print(f'{args.name}: TBD')

    return 0


def _fmt_cmd_list(args: argparse.Namespace) -> int:
    """(V) List named formatting strings associated with commands."""
    print(f'{args.name}: TBD')

    return 0


def _fmt_cmd_add(args: argparse.Namespace) -> int:
    """(V) Add a named formatting string association to a command."""
    print(f'{args.name}: TBD')

    return 0


def _fmt_cmd_del(args: argparse.Namespace) -> int:
    """(V) Remove a named formatting string association with a command."""
    print(f'{args.name}: TBD')

    return 0
