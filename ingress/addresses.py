"""Functions for processing portal addresses."""

from __future__ import annotations

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


def mundane_commands(ctx: app.ArgparseApp):
    """Parser registration API."""
    bm_flags = ctx.get_shared_parser('bookmarks')

    address_type_flag = ctx.argparse_api.ArgumentParser(add_help=False)
    address_type_flag.add_argument(
        '-t',
        '--type',
        action='store',
        required=True,
        help='Address type to modify.')

    address_value_flag = ctx.argparse_api.ArgumentParser(add_help=False)
    address_value_flag.add_argument(
        '-v',
        '--value',
        action='store',
        required=True,
        help='Value portion of address/value to modify.')

    note_flag = ctx.argparse_api.ArgumentParser(add_help=False)
    note_flag.add_argument(
        '-N', '--note', action='store', help='Optional note to add')

    parser = ctx.register_command(address_update, parents=[bm_flags])
    parser.add_argument(
        '-l',
        '--limit',
        action='store',
        type=int,
        default=sys.maxsize,
        help=
        'Maximum number of updates to perform in a run (Default: %(default)s)'
    )

    ctx.register_command(address_type_list)

    parser = ctx.register_command(
        address_type_set, parents=[address_type_flag, note_flag])
    parser.add_argument(
        '-v',
        '--visibility',
        action='store',
        choices=('show', 'hide'),
        help='The visibility of given address type.')

    ctx.register_command(address_type_delete, parents=[address_type_flag])

    ctx.register_command(address_type_value_list)

    parser = ctx.register_command(
        address_type_value_set,
        parents=[address_type_flag, address_value_flag, note_flag])
    parser.add_argument(
        '-p',
        '--pruning',
        action='store',
        choices=('remove', 'ignore'),
        help=(
            'Determines how the pruning operation should treat portals'
            ' with this address type/value.'))

    ctx.register_command(
        address_type_value_delete,
        parents=[address_type_flag, address_value_flag])


# pylint: disable=duplicate-code
def address_update(args: argparse.Namespace) -> int:
    """Update the address related data for portals in a bookmarks file."""
    dbc = args.dbc
    now = time.time()
    portals = bookmarks.load(args.bookmarks)
    _clean(args.dbc)

    fetched = 0
    for portal in portals.values():
        # XXX: Portal fields can be multiple types, so this makes typing
        # happy.
        latlng = str(portal['latlng'])
        address = dbc.session.get(database.Address, latlng)
        if address is None:
            print(f'Fetching for {portal["label"]}')
            address_detail = google.latlng_to_address(latlng)
            db_address = database.Address(
                latlng=latlng, address=address_detail.address, date=now)
            dbc.session.add(db_address)
            _handle_address_type_values(dbc, address_detail)
            dbc.session.commit()
            fetched += 1
            if fetched >= args.limit:
                print(f'Hit fetch limit of {args.limit}')
                break

    return 0


def address_type_list(args: argparse.Namespace) -> int:
    """(V) List the known address types."""
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
            f' | {row.note if row.note else "~~"}')

    return 0


def address_type_set(args: argparse.Namespace) -> int:
    """(V) Update settings on a known address type."""
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


def address_type_delete(args: argparse.Namespace) -> int:
    """(V) Delete a known address type."""
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


def address_type_value_list(args: argparse.Namespace) -> int:
    """(V) List the known address types and values."""
    dbc = args.dbc
    query = dbc.session.query(database.AddressTypeValue).join(
        database.AddressType).filter(
            database.AddressType.visibility != 'hide')
    query = query.order_by(
        database.AddressTypeValue.type, database.AddressTypeValue.value)
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
        f' | {prune_col_header} | Note')
    for row in query:
        print(
            f'{row.type:{type_col_width}}'
            f' | {row.value:{val_col_width}}'
            f' | {row.pruning:^{prune_col_width}}'
            f' | {row.note if row.note else "~~"}')

    return 0


def address_type_value_set(args: argparse.Namespace) -> int:
    """(V) Update settings on a known address type and value."""
    dbc = args.dbc
    address_type_value = dbc.session.get(
        database.AddressTypeValue, (args.type, args.value))
    ret = 0
    if address_type_value is not None:
        if args.pruning is not None:
            address_type_value.pruning = args.pruning
        if args.note is not None:
            address_type_value.note = args.note
        dbc.session.add(address_type_value)
        dbc.session.commit()
    else:
        print(f'Unknown address type/value: "{args.type}"/"{args.value}"')
        ret = 1
    return ret


def address_type_value_delete(args: argparse.Namespace) -> int:
    """(V) Delete a known address type and value."""
    dbc = args.dbc
    address_type_value = dbc.session.get(
        database.AddressTypeValue, (args.type, args.value))
    ret = 0
    if address_type_value is not None:
        dbc.session.delete(address_type_value)
        dbc.session.commit()
    else:
        print(f'Unknown address type: "{args.type}"/"{args.value}"')
        ret = 1
    return ret


def _clean(dbc: database.Database):
    """Clean out old cached data."""
    now = time.time()
    header_printed = False
    oldest_allowed = now - MAX_AGE
    rows = dbc.session.query(
        database.Address).filter(database.Address.date < oldest_allowed)
    for row in rows:
        if not header_printed:
            print('Deleting stale entries')
            header_printed = True
        print(f'{_format_date(float(row.date))} | {row.address}')
        dbc.session.delete(row)

    dbc.session.rollback()


def _format_date(timestamp: float):
    return time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(timestamp))


def _handle_address_type_values(
        dbc: database.Database, detail: google.AddressDetails):
    """Process the type_values field, adding anything that is necessary.

    The caller is responsible for issuing the COMMIT.
    """
    for type_value in detail.type_values:
        address_type = database.AddressType(type=type_value.typ)
        dbc.session.merge(address_type)
        address_type_value = database.AddressTypeValue(
            type=type_value.typ, value=type_value.val)
        dbc.session.merge(address_type_value)
