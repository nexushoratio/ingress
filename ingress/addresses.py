"""Functions for processing portal addresses."""

from __future__ import annotations

import typing

from ingress import database

if typing.TYPE_CHECKING:  # pragma: no cover
    import argparse

    from mundane import app


def mundane_commands(ctx: app.ArgparseApp):
    """Parser registration API."""

    address_type_flag = ctx.argparse_api.ArgumentParser(add_help=False)
    address_type_flag.add_argument(
        '-t',
        '--type',
        action='store',
        required=True,
        help='Address type to modify')

    ctx.register_command(address_type_list)

    parser = ctx.register_command(
        address_type_set, parents=[address_type_flag])
    parser.add_argument(
        '-v',
        '--visibility',
        action='store',
        choices=('show', 'hide'),
        help='The visibility of given address type.')
    parser.add_argument(
        '-N',
        '--note',
        action='store',
        help='Optional note to add to the address type')

    ctx.register_command(address_type_delete, parents=[address_type_flag])


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
