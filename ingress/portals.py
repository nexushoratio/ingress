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


def mundane_commands(ctx: app.ArgparseApp):
    """Register commands."""
    bm_flags = ctx.get_shared_parser('bookmarks_optional')

    parser = ctx.register_command(show, parents=[bm_flags])
    parser.add_argument(
        '-f',
        '--field',
        required=True,
        choices=('first_seen', 'last_seen'),
        help='Sort on this field.')
    parser.add_argument(
        '-s', '--start', action='store', type=_parse_date, help='Start date.')
    parser.add_argument(
        '-S', '--stop', action='store', type=_parse_date, help='Stop date.')
    parser.add_argument(
        '-o',
        '--order',
        action='store',
        choices=('ascend', 'descend'),
        default='ascend',
        help='Sort order.')
    parser.add_argument(
        '-g',
        '--group-by',
        action='store',
        choices=('date',),
        default='date',
        help=(
            'How to group text output.  Grouping by date will group all of'
            ' those on the same calendar date.'))


def show(args: argparse.Namespace) -> int:  # pylint: disable=too-many-locals
    """(V) Show portals sorted by date.

    They can also be exported to a bookmarks file.
    """
    dbc = args.dbc
    start = args.start or 0
    stop = args.stop or float('inf')
    query = dbc.session.query(database.PortalV2)
    if args.field == 'first_seen':
        field = database.PortalV2.first_seen
    if args.field == 'last_seen':
        field = database.PortalV2.last_seen

    query = query.filter(field.between(start, stop))
    groups = collections.defaultdict(list)
    portals = dict()

    dates = list()
    for row in query:
        portal = row.to_iitc()
        portal['date'] = _format_date(portal[args.field])
        dates.append(portal['date'])
        groups[portal[args.group_by]].append(portal)
        portals[row.guid] = portal

    dates.sort()
    text_output = list()
    if dates:
        text_output.append(
            f'{len(dates)} portals {args.field}'
            f' between {dates[0]} and {dates[-1]}\n\n')
    else:
        text_output.append('No portals matched search criteria.')
    for group in sorted(list(groups.keys()), reverse=args.order == 'descend'):
        line = f'{args.group_by.capitalize()}: {group}\n\n'
        groups[group].sort(key=lambda x: x['label'])
        for portal in groups[group]:
            line += (
                '{label}: {date}\n'  # pylint: disable=consider-using-f-string
                'https://www.ingress.com/intel?pll={latlng}\n\n').format(
                    **portal)
            del portal['date']
        text_output.append(line)

    print('=======\n\n'.join(text_output))
    if args.bookmarks:
        bookmarks.save(portals, args.bookmarks)

    return 0


def _parse_date(date_string):
    return time.mktime(time.strptime(date_string, '%Y-%m-%d'))


def _format_date(timestamp):
    return time.strftime('%Y-%m-%d', time.localtime(timestamp))
