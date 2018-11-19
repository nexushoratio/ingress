"""Functions to work with portals directly."""

import collections
import time

from ingress import database


def register_module_parsers(ctx):
    """Parser registration API."""

    parser = ctx.subparsers.add_parser(
        'show-portals', description=show.__doc__, help=show.__doc__)

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
    """Show portals sorted by date."""
    start = args.start or 0
    stop = args.stop or float('inf')
    query = dbc.session.query(database.Portal)
    if args.field == 'first_seen':
        field = database.Portal.first_seen
    if args.field == 'last_seen':
        field = database.Portal.last_seen

    query = query.filter(field.between(start, stop))
    groups = collections.defaultdict(list)
    for row in query:
        portal = dict()
        if args.field == 'first_seen':
            timestamp = row.first_seen
        if args.field == 'last_seen':
            timestamp = row.last_seen
        portal['date'] = _format_date(timestamp)
        portal['code'] = row.code
        portal['label'] = row.label
        portal['latlng'] = row.latlng
        portal['guid'] = row.guid
        groups[portal[args.group_by]].append(portal)

    output = list()
    reverse = args.order == 'descend'
    for group in sorted(groups.keys(), reverse=reverse):
        line = '%s: %s\n\n' % (args.group_by.capitalize(), group)
        groups[group].sort(key=lambda x: x['label'])
        for portal in groups[group]:
            line += ('%(label)s: %(date)s\nhttps://www.ingress.com/intel?'
                     'pll=%(latlng)s\n\n') % portal
        output.append(line)
    note = '=======\n\n'.join(output)
    print note.encode('utf8')


def _parse_date(date_string):
    return time.mktime(time.strptime(date_string, '%Y-%m-%d'))


def _format_date(timestamp):
    return time.strftime('%Y-%m-%d', time.localtime(timestamp))
