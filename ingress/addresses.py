"""Functions for processing portal addresses."""

from __future__ import annotations

import random
import statistics
import sys
import time
import typing

from ingress import bookmarks
from ingress import database
from ingress import google

if typing.TYPE_CHECKING:  # pragma: no cover
    import argparse

    from mundane import app

MAX_AGE = 90 * 24 * 60 * 60


class Error(Exception):
    """Base module exception."""


def mundane_commands(ctx: app.ArgparseApp):
    """Parser registration API."""
    bm_flags = ctx.get_shared_parser('bookmarks')

    type_flag = ctx.argparse_api.ArgumentParser(add_help=False)
    type_flag.add_argument(
        '-t',
        '--type',
        action='store',
        required=True,
        help='Address type to modify.'
    )

    value_flag = ctx.argparse_api.ArgumentParser(add_help=False)
    value_flag.add_argument(
        '-v',
        '--value',
        action='store',
        required=True,
        help='Value portion of (address, value) to modify.'
    )

    note_flag = ctx.argparse_api.ArgumentParser(add_help=False)
    note_flag.add_argument(
        '-N', '--note', action='store', help='Optional note to add'
    )

    parser = ctx.register_command(address, usage_only=True)
    address_cmds = ctx.new_subparser(parser)

    parser = ctx.register_command(
        update, subparser=address_cmds, parents=[bm_flags]
    )
    parser.add_argument(
        '-l',
        '--limit',
        action='store',
        type=int,
        default=sys.maxsize,
        help=
        'Maximum number of updates to perform in a run (Default: %(default)s)'
    )
    parser.add_argument(
        '-d',
        '--delay',
        action='store',
        type=float,
        default=5.0,
        help=(
            'Average random delay, in seconds, between each fetch.'
            '  (Default: %(default)s)'
        )
    )

    parser = ctx.register_command(prune, subparser=address_cmds)
    parser.add_argument(
        '--commit',
        default=False,
        action=ctx.argparse_api.BooleanOptionalAction,
        help='Commit the pruning operation. (Default: %(default)s)'
    )

    parser = ctx.register_command(
        type_, name='type', usage_only=True, subparser=address_cmds
    )
    type_cmds = ctx.new_subparser(parser)

    ctx.register_command(type_list, name='list', subparser=type_cmds)

    parser = ctx.register_command(
        type_set,
        name='set',
        subparser=type_cmds,
        parents=[type_flag, note_flag]
    )
    parser.add_argument(
        '-v',
        '--visibility',
        action='store',
        choices=('show', 'hide'),
        help='The visibility of given address type.'
    )

    ctx.register_command(
        type_del, name='del', subparser=type_cmds, parents=[type_flag]
    )

    parser = ctx.register_command(value, usage_only=True, subparser=type_cmds)
    value_cmds = ctx.new_subparser(parser)

    ctx.register_command(value_list, name='list', subparser=value_cmds)

    parser = ctx.register_command(
        value_set,
        name='set',
        subparser=value_cmds,
        parents=[type_flag, value_flag, note_flag]
    )
    parser.add_argument(
        '-p',
        '--pruning',
        action='store',
        choices=('remove', 'ignore'),
        help=(
            'Determines how the pruning operation should treat portals'
            ' with this address (type, value).'
        )
    )

    ctx.register_command(
        value_del,
        name='del',
        subparser=value_cmds,
        parents=[type_flag, value_flag]
    )


def address(args: argparse.Namespace) -> int:
    """(V) A family of address commands."""
    raise Error('This function should never be called.')


def type_(args: argparse.Namespace) -> int:
    """(V) A family of (address, type) commands."""
    raise Error('This function should never be called.')


def value(args: argparse.Namespace) -> int:
    """(V) A family of (address, type, value) commands."""
    raise Error('This function should never be called.')


# pylint: disable=duplicate-code
def update(args: argparse.Namespace) -> int:
    """(V) Update address related data for portals in a BOOKMARKS file.

    This command uses the Google Maps API to fetch address and other data
    about portal locations.  Run it with the same BOOKMARKS file after the
    'ingest' command.

    In order to run this command, a Google Maps API key must exist in the
    environment variable GOOGLE_API_KEY.

    Hint: A LIMIT may be set to prevent the command from going through your
    quota.

    Hint: See 'address type' and 'address type value' families of commands
    to examine and control how some of this data may be used to affect other
    commands.

    Hint: The 'export' command can be used to generate an initial BOOKMARKS
    file if needed.
    """
    dbc = args.dbc
    delay_base = _tune_delay_base(args.delay)
    now = time.time()
    portals = bookmarks.load(args.bookmarks)
    _clean(args.dbc)

    fetched = 0
    delay = 0.0
    for portal in portals.values():
        latlng = portal['latlng']
        if dbc.session.get(database.Address, latlng) is None:
            if fetched:
                delay = _random_delay(delay_base)
            print(
                f'Fetching for {portal["label"]}'
                f' (delayed by {delay:.2f} seconds)'
            )
            time.sleep(delay)
            address_detail = google.latlng_to_address(latlng)
            db_address = database.Address(
                latlng=latlng, address=address_detail.address, date=now
            )
            dbc.session.add(db_address)
            _handle_address_type_values(dbc, latlng, address_detail)
            dbc.session.commit()
            fetched += 1
            if fetched >= args.limit:
                print(f'Hit fetch limit of {args.limit}')
                break

    return 0


def type_list(args: argparse.Namespace) -> int:
    """(V) List the known address types and current settings.

    These values are populated by the 'address update' command.

    Hint: Use the 'address type set' and 'address type delete' commands to
    modify the settings.
    """
    dbc = args.dbc
    query = dbc.session.query(database.AddressType)
    query = query.order_by(database.AddressType.type)
    type_col_header = 'Type'
    type_col_width = len('administrative_area_level_N')
    vis_col_header = 'Visibility'
    vis_col_width = len(vis_col_header)
    print(f'{type_col_header:^{type_col_width}} | {vis_col_header} | Note')
    for row in query:
        print(
            f'{row.type:{type_col_width}}'
            f' | {row.visibility:^{vis_col_width}}'
            f' | {row.note if row.note else "~~"}'
        )

    return 0


def type_set(args: argparse.Namespace) -> int:
    """(V) Update settings on a known address type.

    Setting the visibility to "hide" will hide it in the
    'address type value list' output and prevent that type from affecting
    dependent operations.

    These values are populated by the 'address update' command.
    """
    dbc = args.dbc
    address_type = dbc.session.get(database.AddressType, args.type)
    ret = 0
    if address_type is not None:
        if args.visibility is not None:
            address_type.visibility = args.visibility
        if args.note is not None:
            address_type.note = args.note
        dbc.session.add(address_type)
        dbc.session.commit()
    else:
        print(f'Unknown address type: "{args.type}"')
        ret = 1
    return ret


def type_del(args: argparse.Namespace) -> int:
    """(V) Delete a known address type.

    Deleting an address type will also delete the related address
    (type, value) combinations.

    Mostly this is used to reduce clutter while fine-tuning settings during
    initial configuration or moving to a new area.

    These values are populated by the 'address update' command.
    """
    dbc = args.dbc
    address_type = dbc.session.get(database.AddressType, args.type)
    ret = 0
    if address_type is not None:
        dbc.session.delete(address_type)
        dbc.session.commit()
    else:
        print(f'Unknown address type: "{args.type}"')
        ret = 1
    return ret


def value_list(args: argparse.Namespace) -> int:
    """(V) List the known address (types, values) and settings.

    These values are populated by the 'address update' command.

    Hint: Use the 'address type value set' and 'address type value del'
    commands to modify the settings.
    """
    dbc = args.dbc
    query = dbc.session.query(database.AddressTypeValue).join(
        database.AddressType
    ).filter(database.AddressType.visibility != 'hide')
    query = query.order_by(
        database.AddressTypeValue.type, database.AddressTypeValue.value
    )
    type_col_header = 'Type'
    type_col_width = len('administrative_area_level_N')
    val_col_header = 'Value'
    # Good random starting number
    val_col_width = 24
    prune_col_header = 'Pruning'
    prune_col_width = len(prune_col_header)
    print(
        f'{type_col_header:^{type_col_width}}'
        f' | {val_col_header:^{val_col_width}}'
        f' | {prune_col_header} | Note'
    )
    for row in query:
        print(
            f'{row.type:{type_col_width}}'
            f' | {row.value:{val_col_width}}'
            f' | {row.pruning:^{prune_col_width}}'
            f' | {row.note if row.note else "~~"}'
        )

    return 0


def value_set(args: argparse.Namespace) -> int:
    """(V) Update settings on a known address (type, value).

    These settings are used to control other commands.

    These values are populated by the 'address update' command.
    """
    dbc = args.dbc
    address_type_value = dbc.session.get(
        database.AddressTypeValue, (args.type, args.value)
    )
    ret = 0
    if address_type_value is not None:
        if args.pruning is not None:
            address_type_value.pruning = args.pruning
        if args.note is not None:
            address_type_value.note = args.note
        dbc.session.add(address_type_value)
        dbc.session.commit()
    else:
        print(f'Unknown address (type, value): "{args.type}"/"{args.value}"')
        ret = 1
    return ret


def value_del(args: argparse.Namespace) -> int:
    """(V) Delete a known address (type, value).

    Mostly this is used for testing.

    These values are populated by the 'address update' command.
    """
    dbc = args.dbc
    address_type_value = dbc.session.get(
        database.AddressTypeValue, (args.type, args.value)
    )
    ret = 0
    if address_type_value is not None:
        dbc.session.delete(address_type_value)
        dbc.session.commit()
    else:
        print(f'Unknown address type: "{args.type}"/"{args.value}"')
        ret = 1
    return ret


def prune(args: argparse.Namespace) -> int:
    """(V) Remove portals from the database that do not match criteria.

    Prune portals from the database where its address has an
    (type, value) for the pruning operation set to "remove".

    Hint: See the 'address update', 'address type', and
    'address type value' families of commands for more information.
    """
    dbc = args.dbc

    query = dbc.session.query(database.PortalV2)
    query = query.join(
        database.AddressTypeValueAssociation, database.PortalV2.latlng ==
        database.AddressTypeValueAssociation.latlng
    )
    query = query.join(database.AddressTypeValue)
    query = query.filter(database.AddressTypeValue.pruning == 'remove')
    query = query.join(database.AddressType)
    query = query.filter(database.AddressType.visibility != 'hide')

    for portal in query:
        print(f'Pruning {portal.guid} - {portal.label}')
        dbc.session.delete(portal)

    if args.commit:
        dbc.session.commit()
    else:
        dbc.session.rollback()

    return 0


def _clean(dbc: database.Database):
    """Clean out old cached data."""
    now = time.time()
    header_printed = False
    oldest_allowed = now - MAX_AGE
    rows = dbc.session.query(database.Address
                             ).filter(database.Address.date < oldest_allowed
                                      ).limit(30)
    for row in rows:
        if not header_printed:
            print('Deleting stale entries')
            header_printed = True
        print(f'{_format_date(float(row.date))} | {row.address}')
        dbc.session.delete(row)

    dbc.session.commit()


def _format_date(timestamp: float):
    return time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(timestamp))


def _handle_address_type_values(
    dbc: database.Database, latlng: str, detail: google.AddressDetails
):
    """Process the type_values field, updating the database as appropriate.

    The caller is responsible for issuing the COMMIT.
    """
    for type_value in detail.type_values:
        address_type = database.AddressType(type=type_value.typ)
        dbc.session.merge(address_type)
        address_type_value = database.AddressTypeValue(
            type=type_value.typ, value=type_value.val
        )
        dbc.session.merge(address_type_value)
        association = database.AddressTypeValueAssociation(
            latlng=latlng, type=type_value.typ, value=type_value.val
        )
        dbc.session.merge(association)


def _random_delay(base: float) -> float:
    """Get a random number to sleep."""
    return abs(
        random.weibullvariate(base, 1.5)
        - random.weibullvariate(base / 2, 1.25)
    )


def _tune_delay_base(target: float) -> float:
    """Find a base for the delay function that gets close to the target."""
    base = target

    def mean(num: float) -> float:
        return statistics.mean([_random_delay(num) for _ in range(10000)])

    while mean(base) < target:
        base *= 1.05
    while mean(base) > target:
        base *= 0.99

    return base
