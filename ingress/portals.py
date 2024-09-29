"""Functions to work with portals directly."""

from __future__ import annotations

import collections
import typing

from ingress import bookmarks
from ingress import database

if typing.TYPE_CHECKING:  # pragma: no cover
    import argparse

    from mundane import app

Statement: typing.TypeAlias = database.sqlalchemy.sql.selectable.Select
StatementUpdater: typing.TypeAlias = typing.Callable[[Statement], Statement]

Row: typing.TypeAlias = database.sqlalchemy.engine.row.Row
RowBuilder: typing.TypeAlias = typing.Callable[[Row], str]

ORDER_BY: dict[str, StatementUpdater] = dict()
GROUP_BY: dict[str, RowBuilder] = dict()


def mundane_commands(ctx: app.ArgparseApp):
    """Register commands."""
    bm_flags = ctx.get_shared_parser('bookmarks_optional')

    parser = ctx.register_command(show, parents=[bm_flags])
    parser.add_argument(
        '-q', '--query', action='count', default=0, help='Show SQL query.')
    parser.add_argument(
        '-l', '--limit', action='store', help='Limit the number of results.')
    parser.add_argument(
        '-o',
        '--order-by',
        action='append',
        choices=ORDER_BY.keys(),
        help='Sort results on these fields.')
    parser.add_argument(
        '--first-seen-after',
        help='Restrict to portals first seen after this date')
    parser.add_argument(
        '--first-seen-before',
        help='Restrict to portals first seen before this date')
    parser.add_argument(
        '--last-seen-after',
        help='Restrict to portals last seen after this date')
    parser.add_argument(
        '--last-seen-before',
        help='Restrict to portals last seen before this date')
    parser.add_argument(
        '-g',
        '--group-by',
        action='append',
        choices=GROUP_BY.keys(),
        help='Group portals by the specified fields.')


def show(args: argparse.Namespace) -> int:  # pylint: disable=too-many-branches,too-many-locals
    """Show portals selected and sorted by criteria.

    They can also be exported to a bookmarks file.
    """
    dbc = args.dbc
    sqla = database.sqlalchemy

    criteria = list()
    group_by: list[RowBuilder] = list()
    first_seen = sqla.sql.func.date(
        database.PortalV2.first_seen, 'unixepoch',
        'localtime').label('local_first_seen')
    last_seen = sqla.sql.func.date(
        database.PortalV2.last_seen, 'unixepoch',
        'localtime').label('local_last_seen')
    stmt = sqla.select(database.PortalV2, first_seen, last_seen)

    if args.first_seen_after:
        stmt = stmt.where(first_seen >= args.first_seen_after)
        criteria.append(f'First Seen After: {args.first_seen_after}')
    if args.first_seen_before:
        stmt = stmt.where(first_seen < args.first_seen_before)
        criteria.append(f'First Seen Before: {args.first_seen_before}')
    if args.last_seen_after:
        stmt = stmt.where(last_seen >= args.last_seen_after)
        criteria.append(f'Last Seen After: {args.last_seen_after}')
    if args.last_seen_before:
        stmt = stmt.where(last_seen < args.last_seen_before)
        criteria.append(f'Last Seen Before: {args.last_seen_before}')
    if args.order_by:
        for order in args.order_by:
            stmt = ORDER_BY[order](stmt)
    if args.group_by:
        group_by.extend(GROUP_BY[group] for group in args.group_by)
    if args.limit:
        stmt = stmt.limit(args.limit)

    if args.query:
        print(
            stmt.compile(
                dbc.session.get_bind(),
                compile_kwargs={"literal_binds": True}))
        return 0

    portals: bookmarks.Portals = dict()
    groups = collections.defaultdict(list)

    for row in dbc.session.execute(stmt):
        group = tuple(fn(row) for fn in group_by)
        portal = row.PortalV2.to_iitc()
        groups[group].append(portal)
        portals[portal['guid']] = portal

    text_output = list()
    text_output.append(
        f'Portals matching the search criteria: {len(portals)}\n'
        f'  {", ".join(criteria)}\n\n')
    for group in groups:
        line = ''
        if group:
            line += f'{", ".join(group)}\n\n'
        for portal in groups[group]:
            line += (
                '{label}\n'  # pylint: disable=consider-using-f-string
                'https://www.ingress.com/intel?pll={latlng}\n\n').format(
                    **portal)
        text_output.append(line)

    print('=======\n\n'.join(text_output))
    if args.bookmarks:
        bookmarks.save(portals, args.bookmarks)

    return 0


def _order_by_first_seen(stmt: Statement) -> Statement:
    return stmt.order_by(stmt.exported_columns.get('local_first_seen'))


def _order_by_last_seen(stmt: Statement) -> Statement:
    return stmt.order_by(stmt.exported_columns.get('local_last_seen'))


def _order_by_label(stmt: Statement) -> Statement:
    return stmt.order_by(stmt.exported_columns.get('label'))


def _group_by_first_seen(row: Row) -> str:
    """Extract and format first_seen column."""
    return f'First seen: {row.local_first_seen}'  # type: ignore[attr-defined]


def _group_by_last_seen(row: Row) -> str:
    """Extract and format last_seen column."""
    return f'Last seen: {row.local_last_seen}'  # type: ignore[attr-defined]


ORDER_BY.update(
    {
        'first-seen': _order_by_first_seen,
        'last-seen': _order_by_last_seen,
        'label': _order_by_label,
    })

GROUP_BY.update(
    {
        'first-seen': _group_by_first_seen,
        'last-seen': _group_by_last_seen,
    })
