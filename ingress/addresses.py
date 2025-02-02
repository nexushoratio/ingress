"""Functions for processing portal addresses."""

from __future__ import annotations

import dataclasses
import logging
import os
import random
import statistics
import time
import typing

from mundane import constants

from ingress import bookmarks
from ingress import database
from ingress import google

if typing.TYPE_CHECKING:  # pragma: no cover
    import argparse

    from mundane import app

sqla = database.sqlalchemy

_DAILY_FETCHES_ENVVAR: str = 'INGRESS_DAILY_FETCHES'


class Error(Exception):
    """Base module exception."""


@dataclasses.dataclass
class UpdateOutputTemplate:
    """Describes current values used for the output of update."""
    data: dict[str, typing.Any] = dataclasses.field(init=False)
    row: str = dataclasses.field(init=False)
    header: str = dataclasses.field(init=False)


def mundane_commands(ctx: app.ArgparseApp):
    """Parser registration API."""
    bm_flags = ctx.safe_get_shared_parser('bookmarks')
    bm_label_flags = ctx.safe_get_shared_parser('bookmark_label')

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

    address_cmds = ctx.new_subparser(
        ctx.register_command(_address, name='address', usage_only=True)
    )

    parser = ctx.register_command(
        update, subparser=address_cmds, parents=[bm_flags]
    )
    parser.add_argument(
        '-l',
        '--limit',
        action='store',
        type=int,
        help='Maximum number of updates to perform in a run.'
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
    parser.add_argument(
        '--daily-updates',
        action='store',
        type=int,
        default=os.getenv(_DAILY_FETCHES_ENVVAR, '100'),
        help=(
            'The typical number of updates expected in a day.  In order to'
            ' maintain data freshness, older entries are removed.  How old'
            ' values are allowed to get is computed by dividing the number of'
            ' portals by DAILY_UPDATES.  It is expected that the number of'
            ' updates performed in a day will be low in order to keep under'
            ' API quotas.  A default value for this flag may be set via the'
            f' environment variable "{_DAILY_FETCHES_ENVVAR}".  (Default:'
            ' %(default)s)'
        )
    )

    parser = ctx.register_command(
        prune, subparser=address_cmds, parents=[bm_label_flags]
    )
    parser.add_argument(
        '--commit',
        default=False,
        action=ctx.argparse_api.BooleanOptionalAction,
        help='Commit the pruning operation. (Default: %(default)s)'
    )

    type_cmds = ctx.new_subparser(
        ctx.register_command(
            _type, name='type', usage_only=True, subparser=address_cmds
        )
    )

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

    value_cmds = ctx.new_subparser(
        ctx.register_command(
            _value, name='value', usage_only=True, subparser=type_cmds
        )
    )

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


def _address(args: argparse.Namespace) -> int:
    """(V) A family of address commands."""
    raise Error('This function should never be called.')


def _type(args: argparse.Namespace) -> int:
    """(V) A family of (address, type) commands."""
    raise Error('This function should never be called.')


def _value(args: argparse.Namespace) -> int:
    """(V) A family of (address, type, value) commands."""
    raise Error('This function should never be called.')


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
    _clean(args)

    dbc = args.dbc

    delay_base = _tune_delay_base(args.delay)
    portals = bookmarks.load(args.bookmarks)
    template = _assemble_update_template(args)
    fetched = 0
    delay = 0.0
    for portal in portals.values():
        latlng = portal['latlng']
        if dbc.session.get(database.Address, latlng) is None:
            if fetched:
                delay = _random_delay(delay_base)
            template.data.update(
                {
                    'current': fetched + 1,
                    'label': portal['label'],
                    'delay': delay,
                }
            )
            if fetched % 20 == 0:
                print(template.header.format_map(template.data))
            print(template.row.format_map(template.data))

            time.sleep(delay)
            address_detail = google.latlng_to_address(latlng)
            now = int(time.time())
            db_address = database.Address(
                latlng=latlng, address=address_detail.address, date=now
            )
            dbc.session.add(db_address)
            _handle_address_type_values(dbc, latlng, address_detail)
            dbc.session.commit()
            fetched += 1
            if args.limit is not None and fetched >= args.limit:
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

    stmt = sqla.select(database.AddressType
                       ).order_by(database.AddressType.type)

    type_col_header = 'Type'
    type_col_width = len('administrative_area_level_N')
    vis_col_header = 'Visibility'
    vis_col_width = len(vis_col_header)

    print(f'{type_col_header:^{type_col_width}} | {vis_col_header} | Note')
    for row in dbc.session.execute(stmt):
        atype = row.AddressType
        print(
            f'{atype.type:{type_col_width}}'
            f' | {atype.visibility:^{vis_col_width}}'
            f' | {atype.note or "~~"}'
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

    stmt = (
        sqla.select(database.AddressTypeValue, database.AddressType).join(
            database.AddressTypeValue,
            database.AddressTypeValue.type == database.AddressType.type
        ).where(database.AddressType.visibility != 'hide').order_by(
            database.AddressTypeValue.type, database.AddressTypeValue.value
        )
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
    for row in dbc.session.execute(stmt):
        atv = row.AddressTypeValue
        print(
            f'{atv.type:{type_col_width}}'
            f' | {atv.value:{val_col_width}}'
            f' | {atv.pruning:^{prune_col_width}}'
            f' | {atv.note or "~~"}'
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

    With no options, only the list of portals that might be pruned are
    displayed.  The --commit flag will perform the deletions.

    Alternatively, the --bookmark flag will save the list in an internal
    bookmark folder.  A folder LABEL may be passed as an option to --bookmark,
    otherwise it will be named "prune".  See the 'bookmark' family of commands
    for more information.

    Hint: See the 'address update', 'address type', and 'address type value'
    families of commands for more information.
    """
    dbc = args.dbc

    guids = set()

    stmt = sqla.select(database.PortalV2)
    stmt = stmt.join(
        database.AddressTypeValueAssociation, database.PortalV2.latlng ==
        database.AddressTypeValueAssociation.latlng
    )
    stmt = stmt.join(database.AddressTypeValue)
    stmt = stmt.where(database.AddressTypeValue.pruning == 'remove')
    stmt = stmt.join(database.AddressType)
    stmt = stmt.where(database.AddressType.visibility != 'hide')

    for row in dbc.session.execute(stmt):
        portal = row.PortalV2
        print(f'Pruning {portal.guid} - {portal.label}')
        guids.add(portal.guid)
        dbc.session.delete(portal)

    if args.commit:
        dbc.session.commit()
    else:
        dbc.session.rollback()
        if args.bookmark and guids:
            use_default = args.bookmark == bookmarks.DEFAULT_FOLDER
            label = args.name if use_default else args.bookmark
            existing = args.existing_mode
            folder = bookmarks.prepare_folder(dbc, label, existing)
            for guid in guids:
                dbc.session.add(
                    database.PortalBookmark(
                        folder_id=folder.uuid, portal_id=guid
                    )
                )
            dbc.session.commit()

    return 0


DELAY = 'Delay'


def _assemble_update_template(
    args: argparse.Namespace
) -> UpdateOutputTemplate:
    """Assemble values for the header and row templates."""
    delay = f'{max(_random_delay(args.delay) for _ in range(10000)):.2f}'
    template = UpdateOutputTemplate()
    template.data = {
        'nul': '',
        'limit': args.limit,
        'current_width': 5,
        'delay_width': max(len(DELAY), len(delay)),
        'delay_str': DELAY,
    }
    template.data['delay_nul'
                  ] = (len(DELAY) - template.data['delay_width']) % 2
    template.data['delay_str_width'] = template.data[
        'delay_width'] - template.data['delay_nul']
    headers = list()
    if args.limit is None:
        template.row = ' {current:{current_width}} '
        headers.append('Fetch #')
    else:
        template.row = ' {current:{current_width}} /{limit:{current_width}}'
        headers.append('Fetch #/Limit')
    template.row += ' | {delay:{delay_width}.2f} | {label}'
    headers.extend(
        ('{nul:{delay_nul}}{delay_str:^{delay_str_width}}', 'Label')
    )
    template.header = '\n' + ' | '.join(headers)
    return template


def _clean(args: argparse.Namespace):
    """Clean out old cached data."""
    dbc = args.dbc

    stmt = sqla.select(sqla.func.count()).select_from(database.PortalV2)
    count = dbc.session.scalar(stmt)
    max_days = count // args.daily_updates
    max_age = max_days * constants.SECONDS_PER_DAY
    logging.info(
        'At the expected fetch rate of %d, it would take %d days to refresh',
        args.daily_updates, max_days
    )

    limit = 25
    if args.limit is not None:
        limit = args.limit // 2

    now = time.time()
    header_printed = False
    oldest_allowed = now - max_age
    stmt = sqla.select(database.Address
                       ).where(database.Address.date < oldest_allowed
                               ).order_by(database.Address.date).limit(limit)
    for row in dbc.session.execute(stmt):
        addr = row.Address
        if not header_printed:
            print(f'Deleting up to {limit} stale entries:')
            header_printed = True
        print(f'{_format_date(float(addr.date))} | {addr.address}')
        dbc.session.delete(addr)

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
