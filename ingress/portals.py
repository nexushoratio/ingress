"""Functions to work with portals directly."""

from __future__ import annotations

import collections
import time
import typing

from ingress import bookmarks
from ingress import database

if typing.TYPE_CHECKING:  # pragma: no cover
    import argparse

    from mundane import app

Query: typing.TypeAlias = database.sqlalchemy.orm.query.Query
QueryUpdater: typing.TypeAlias = typing.Callable[[Query], Query]

Row: typing.TypeAlias = database.sqlalchemy.engine.row.Row
RowBuilder: typing.TypeAlias = typing.Callable[[Row], str]

ORDER_BY: dict[str, QueryUpdater] = dict()
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
        type=_parse_date,
        help='Restrict to portals first seen after this date')
    parser.add_argument(
        '--first-seen-before',
        type=_parse_date,
        help='Restrict to portals first seen before this date')
    parser.add_argument(
        '--last-seen-after',
        type=_parse_date,
        help='Restrict to portals last seen after this date')
    parser.add_argument(
        '--last-seen-before',
        type=_parse_date,
        help='Restrict to portals last seen before this date')
    parser.add_argument(
        '-g',
        '--group-by',
        action='append',
        choices=GROUP_BY.keys(),
        help=(
            'Group portals by the specified fields.  Date oriented fields'
            ' will be converted to a calendar date.'))


def show(args: argparse.Namespace) -> int:  # pylint: disable=too-many-branches
    """Show portals selected and sorted by criteria.

    They can also be exported to a bookmarks file.
    """
    dbc = args.dbc

    criteria = list()
    group_by: list[RowBuilder] = list()
    query = dbc.session.query(database.PortalV2, database.Address)
    query = query.outerjoin(
        database.Address, database.PortalV2.latlng == database.Address.latlng)
    if args.first_seen_after:
        query = query.filter(
            database.PortalV2.first_seen > args.first_seen_after)
        criteria.append(
            f'First Seen After: {_format_date(args.first_seen_after)}')
    if args.first_seen_before:
        query = query.filter(
            database.PortalV2.first_seen < args.first_seen_before)
        criteria.append(
            f'First Seen Before: {_format_date(args.first_seen_before)}')
    if args.last_seen_after:
        query = query.filter(
            database.PortalV2.last_seen > args.last_seen_after)
        criteria.append(
            f'Last Seen After: {_format_date(args.last_seen_after)}')
    if args.last_seen_before:
        query = query.filter(
            database.PortalV2.last_seen > args.last_seen_before)
        criteria.append(
            f'Last Seen Before: {_format_date(args.last_seen_before)}')
    if args.order_by:
        for order in args.order_by:
            query = ORDER_BY[order](query)
    if args.group_by:
        group_by.extend(GROUP_BY[group] for group in args.group_by)
    if args.limit:
        query = query.limit(args.limit)
    if args.query:
        print(query)
        return 0

    portals: bookmarks.Portals = dict()
    groups = collections.defaultdict(list)

    for row in query:
        group = tuple(fn(row) for fn in group_by)
        portal = row.PortalV2.to_iitc()
        groups[group].append(portal)
        portals[portal['guid']] = portal

    text_output = list()
    text_output.append(
        f'Portals matching the search criteria: {len(portals)}\n'
        f'  {", ".join(criteria)}\n\n')
    for group in groups:
        line = f'{", ".join(group)}\n\n'
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


def _parse_date(date_string):
    return time.mktime(time.strptime(date_string, '%Y-%m-%d'))


def _format_date(timestamp):
    return time.strftime('%Y-%m-%d', time.localtime(timestamp))


def _order_by_first_seen(query: Query) -> Query:
    return query.order_by(database.PortalV2.first_seen)


def _order_by_last_seen(query: Query) -> Query:
    return query.order_by(database.PortalV2.last_seen)


def _order_by_label(query: Query) -> Query:
    return query.order_by(database.PortalV2.label)


def _group_by_first_seen(row: Row) -> str:
    """Extract and format first_seen column."""
    date = _format_date(row.PortalV2.first_seen)  # type: ignore[attr-defined]
    return f'First seen: {date}'


def _group_by_last_seen(row: Row) -> str:
    """Extract and format last_seen column."""
    date = _format_date(row.PortalV2.last_seen)  # type: ignore[attr-defined]
    return f'Last seen: {date}'


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
