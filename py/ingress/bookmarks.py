"""Functions to work with IITC bookmarks files."""

import glob
import itertools
import logging
import os

from ingress import database
from ingress import json
from ingress import zcta as zcta_lib


def register_shared_parsers(ctx):
    """Parser registration API."""
    bm_parser = ctx.argparse.ArgumentParser(add_help=False)
    bm_parser.add_argument(
        '-b',
        '--bookmarks',
        action='store',
        required=True,
        help='IITC bookmarks json file to use')

    glob_parser = ctx.argparse.ArgumentParser(add_help=False)
    glob_parser.add_argument(
        '-g',
        '--glob',
        action='append',
        required=True,
        type=glob.iglob,
        help=('A filename glob that will be matched by the program'
              ' instead of the shell.  May be specified multiple times.'))

    ctx.shared_parsers['bm_parser'] = bm_parser
    ctx.shared_parsers['glob_parser'] = glob_parser


def register_module_parsers(ctx):
    """Parser registration API."""
    bm_parser = ctx.shared_parsers['bm_parser']
    glob_parser = ctx.shared_parsers['glob_parser']

    parser_import = ctx.subparsers.add_parser(
        'import',
        parents=[bm_parser],
        description=import_bookmarks.__doc__,
        help=import_bookmarks.__doc__)
    parser_import.set_defaults(func=import_bookmarks)

    parser_find_missing_labels = ctx.subparsers.add_parser(
        'find-missing-labels',
        parents=[bm_parser, glob_parser],
        description=find_missing_labels.__doc__,
        help=find_missing_labels.__doc__)
    parser_find_missing_labels.set_defaults(func=find_missing_labels)

    parser = ctx.subparsers.add_parser(
        'merge-bookmarks',
        parents=[bm_parser, glob_parser],
        description=merge.__doc__,
        help=merge.__doc__)
    parser.set_defaults(func=merge)


def import_bookmarks(args, dbc):
    """Update the database with portals listed in a bookmarks file."""
    portals = load(args.bookmarks)
    timestamp = os.stat(args.bookmarks).st_mtime

    zcta = zcta_lib.Zcta()
    for portal in portals.itervalues():
        portal['last_seen'] = timestamp
        portal['code'] = zcta.code_from_latlng(portal['latlng'])

    keys = set(portals.keys())
    rows = dbc.session.query(database.Portal).filter(
        database.Portal.guid.in_(keys))
    for row in rows:
        guid = row.guid
        portal = portals[guid]
        # only update if newer
        if portal['last_seen'] > row.last_seen:
            row.update(**portal)
        # or if we have an updated code
        elif portal['latlng'] == row.latlng and portal['code'] != row.code:
            row.code = portal['code']

        keys.remove(guid)

    # whatever is left is a new portal
    known_columns = [x.key for x in database.Portal.__table__.columns]  # pylint: disable=no-member

    for key in keys:
        portal = portals[key]
        portal['first_seen'] = timestamp
        new_portal = dict((k, portal[k]) for k in known_columns)
        db_portal = database.Portal(**new_portal)
        dbc.session.add(db_portal)

    dbc.session.commit()


def load(filename):
    """Load a particular bookmarks file returning a dict of portals."""
    bookmarks = json.load(filename)
    portals_by_folder = bookmarks['portals']
    portals = dict()
    for folder in portals_by_folder.itervalues():
        portals_in_folder = folder['bkmrk']
        for portal in portals_in_folder.itervalues():
            guid = portal['guid']
            portals[guid] = portal

    logging.info('%s portals loaded', len(portals))
    return portals


def save(portals, filename):
    """Save a dictionary of portals into a particular bookmarks file."""
    new_bookmarks = new()
    new_bookmarks['portals']['idOthers']['bkmrk'] = portals
    json.save(filename, new_bookmarks)


def find_missing_labels(args, dbc):
    """Look through globs of bookmarks for missing labels.

    It will remove portals with missing labels from the bookmarks and
    add them to a newly created bookmarks file instead.  The contents of
    the destination bookmarks file will be destroyed.
    """
    missing_portals = dict()
    save(missing_portals, args.bookmarks)
    for filename in itertools.chain(*args.glob):
        missing_guids = set()
        portals = load(filename)
        for portal in portals.itervalues():
            if not portal.has_key('label'):
                missing_guids.add(portal['guid'])
        if missing_guids:
            for guid in missing_guids:
                missing_portals[guid] = portals[guid]
                del portals[guid]
            save(missing_portals, args.bookmarks)
            ftime = os.stat(filename)
            save(portals, filename)
            os.utime(filename, (ftime.st_atime, ftime.st_mtime))


def merge(args, dbc):
    """Merge multiple bookmarks files into one.

    Inputs will be the files specified by the glob arguments.  The
    contents of the destination bookmarks file will be destroyed.
    """
    portals = dict()
    save(portals, args.bookmarks)
    for filename in itertools.chain(*args.glob):
        portals.update(load(filename))

    save(portals, args.bookmarks)


def new():
    """Create a new, empty bookmarks object."""
    bookmarks = {
        'maps': {
            'idOthers': {
                'bkmrk': {},
                'label': 'Others',
                'state': 1,
            },
        },
        'portals': {
            'idOthers': {
                'bkmrk': {},
                'label': 'Others',
                'state': 0,
            },
        },
    }
    return bookmarks
