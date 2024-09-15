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

    parser = ctx.register_command(address_prune)
    parser.add_argument(
        '--commit',
        default=False,
        action=ctx.argparse_api.BooleanOptionalAction,
        help='Commit the pruning operation. (Default: %(default)s)')


# pylint: disable=duplicate-code
def address_update(args: argparse.Namespace) -> int:
    """(V) Update address related data for portals in a BOOKMARKS file.

    This command uses the Google Maps API to fetch address and other data
    about portal locations.  Run it with the same BOOKMARKS file after the
    'ingest' command.

    In order to run this command, a Google Maps API key must exist in the
    environment variable GOOGLE_API_KEY.

    Hint: A LIMIT may be set to prevent the command from going through your
    quota.

    Hint: See 'address-type-*' and 'address-type-value-*' family of commands
    to examine and control how some of this data may be used to affect other
    commands.

    Hint: The 'export' command can be used to generate an initial BOOKMARKS
    file if needed.
    """
    dbc = args.dbc
    now = time.time()
    portals = bookmarks.load(args.bookmarks)
    _clean(args.dbc)

    fetched = 0
    for portal in portals.values():
        latlng = portal['latlng']
        address = dbc.session.get(database.Address, latlng)
        if address is None:
            print(f'Fetching for {portal["label"]}')
            address_detail = google.latlng_to_address(latlng)
            db_address = database.Address(
                latlng=latlng, address=address_detail.address, date=now)
            dbc.session.add(db_address)
            _handle_address_type_values(dbc, latlng, address_detail)
            dbc.session.commit()
            fetched += 1
            if fetched >= args.limit:
                print(f'Hit fetch limit of {args.limit}')
                break

    return 0


def address_type_list(args: argparse.Namespace) -> int:
    """(V) List the known address types and current settings.

    These values are populated by the 'address-update' command.

    Hint: Use the 'address-type-set' and 'address-type-delete' commands to
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
            f' | {row.note if row.note else "~~"}')

    return 0


def address_type_set(args: argparse.Namespace) -> int:
    """(V) Update settings on a known address type.

    Setting the visibility to "hide" will hide it in the
    'address-type-value-list' output and prevent the type from affecting
    dependent operations.

    These values are populated by the 'address-update' command.
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


def address_type_delete(args: argparse.Namespace) -> int:
    """(V) Delete a known address type.

    Deleting an address type will also delete the related (address, type,
    value) combinations.

    Mostly this is used to reduce clutter while fine-tuning settings during
    initial configuration or moving to a new area.

    These values are populated by the 'address-update' command.
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


def address_type_value_list(args: argparse.Namespace) -> int:
    """(V) List the known address (types, values) and settings.

    These values are populated by the 'address-update' command.

    Hint: Use the 'address-type-value-set' and 'address-type-value-delete'
    commands to modify the settings.
    """
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
    """(V) Update settings on a known address (type, value).

    These settings are used to control other commands.

    These values are populated by the 'address-update' command.
    """
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
    """(V) Delete a known address (type, value).

    Mostly this is used for testing.

    These values are populated by the 'address-update' command.
    """
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


def address_prune(args: argparse.Namespace) -> int:
    """(V) Remove portals from the database that do not match criteria.

    Prune portals from the database where its address has an
    address-type-value for the pruning operation set to "remove".

    Hint: See the 'address-update', 'address-type-*', and
    'address-type-value-*' family of command for more information.
    """
    dbc = args.dbc

    query = dbc.session.query(database.PortalV2)
    query = query.join(
        database.AddressTypeValueAssociation, database.PortalV2.latlng ==
        database.AddressTypeValueAssociation.latlng)
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
        dbc: database.Database, latlng: str, detail: google.AddressDetails):
    """Process the type_values field, updating the database as appropriate.

    The caller is responsible for issuing the COMMIT.
    """
    for type_value in detail.type_values:
        address_type = database.AddressType(type=type_value.typ)
        dbc.session.merge(address_type)
        address_type_value = database.AddressTypeValue(
            type=type_value.typ, value=type_value.val)
        dbc.session.merge(address_type_value)
        association = database.AddressTypeValueAssociation(
            latlng=latlng, type=type_value.typ, value=type_value.val)
        dbc.session.merge(association)
