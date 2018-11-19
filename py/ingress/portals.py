"""Functions to work with portals directly."""

import collections
import time

from ingress import bookmarks
from ingress import database


def register_module_parsers(ctx):
    """Parser registration API."""
    bm_parser = ctx.shared_parsers['bm_parser']

    parser = ctx.subparsers.add_parser(
        'show-portals',
        parents=[bm_parser],
        description=show.__doc__,
        help=show.__doc__)

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
        choices=('code', 'date'),
        default='code',
        help=('How to group text output.  Grouping by date will group all of'
              ' those on the same calendar date.'))
    parser.set_defaults(func=show)


def show(args, dbc):
    """Show portals sorted by date.

    They will be exported to a bookmarks file.
    """
    start = args.start or 0
    stop = args.stop or float('inf')
    query = dbc.session.query(database.Portal)
    if args.field == 'first_seen':
        field = database.Portal.first_seen
    if args.field == 'last_seen':
        field = database.Portal.last_seen

    query = query.filter(field.between(start, stop))
    groups = collections.defaultdict(list)
    portals = dict()
    known_columns = frozenset(x.key for x in database.Portal.__table__.columns)  # pylint: disable=no-member

    for row in query:
        portal = dict()
        for column in known_columns:
            portal[column] = getattr(row, column)
        portal['date'] = _format_date(portal[args.field])
        groups[portal[args.group_by]].append(portal)
        portals[row.guid] = portal

    text_output = list()
    for group in sorted(groups.keys(), reverse=args.order == 'descend'):
        line = '%s: %s\n\n' % (args.group_by.capitalize(), group)
        groups[group].sort(key=lambda x: x['label'])
        for portal in groups[group]:
            line += ('%(label)s: %(date)s\nhttps://www.ingress.com/intel?'
                     'pll=%(latlng)s\n\n') % portal
        text_output.append(line)

    print '=======\n\n'.join(text_output).encode('utf8')
    _save_cleaned_bookmarks(portals, known_columns, args.bookmarks)


def _save_cleaned_bookmarks(portals, known_columns, filename):
    for portal in portals.itervalues():
        keys_to_delete = set()
        for key in portal.iterkeys():
            if key not in known_columns:
                keys_to_delete.add(key)
        for key in keys_to_delete:
            del portal[key]
    bookmarks.save(portals, filename)


def _parse_date(date_string):
    return time.mktime(time.strptime(date_string, '%Y-%m-%d'))


def _format_date(timestamp):
    return time.strftime('%Y-%m-%d', time.localtime(timestamp))
