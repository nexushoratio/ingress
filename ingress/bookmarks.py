"""Functions to work with IITC bookmarks files."""

from __future__ import annotations

import glob
import itertools
import logging
import os
import typing

from ingress import database
from ingress import json

if typing.TYPE_CHECKING:  # pragma: no cover
    import argparse

    from mundane import app


def mundane_shared_flags(ctx: app.ArgparseApp):
    """Register shared flags."""
    parser = ctx.new_shared_parser('bookmarks')
    if parser:
        parser.add_argument(
            '-b',
            '--bookmarks',
            action='store',
            required=True,
            help='IITC bookmarks json file to use')

    parser = ctx.new_shared_parser('glob')
    if parser:
        parser.add_argument(
            '-g',
            '--glob',
            action='append',
            required=True,
            type=glob.iglob,  # type: ignore[arg-type]  # old version of mypy
            help=(
                'A filename glob that will be matched by the program'
                ' instead of the shell.  May be specified multiple times.'))


def mundane_commands(ctx: app.ArgparseApp):
    """Register commands."""
    bm_flags = ctx.get_shared_parser('bookmarks')
    glob_flags = ctx.get_shared_parser('glob')

    ctx.register_command(ingest, parents=[bm_flags])
    ctx.register_command(expunge, parents=[bm_flags])

    parser = ctx.register_command(export, parents=[bm_flags])
    parser.add_argument(
        '-s',
        '--samples',
        action='store',
        default=None,
        type=int,
        help='Roughly how many portals should be in the output.')

    parser = ctx.register_command(flatten, parents=[bm_flags])
    parser.add_argument(
        '-s',
        '--size',
        action='store',
        default=3 * 1024 * 1024,
        type=int,
        help='Rough upper limit on the size of each flattened output file.')
    parser.add_argument(
        '-p',
        '--pattern',
        action='store',
        default='flattened-{size}-{count:0{width}d}.json',
        help=(
            'Pattern used to name the output files.  Uses PEP 3101 formatting '
            'strings with the following fields:  size, width, count'))

    ctx.register_command(find_missing_labels, parents=[bm_flags, glob_flags])
    ctx.register_command(merge, parents=[bm_flags, glob_flags])


def ingest(args: argparse.Namespace) -> int:
    """(V) Update the database with portals listed in a bookmarks file."""
    dbc = args.dbc
    portals = load(args.bookmarks)
    timestamp = os.stat(args.bookmarks).st_mtime

    for portal in portals.values():
        portal['last_seen'] = timestamp

    # Look for existing portals first
    rows = dbc.session.query(database.Portal).filter(
        database.Portal.guid.in_(portals))
    for row in rows:
        guid = row.guid
        portal = portals[guid]
        # only update if newer
        if portal['last_seen'] > row.last_seen:
            row.from_iitc(**portal)

        del portals[guid]

    # Whatever is left is a new portal
    for portal in portals.values():
        portal['first_seen'] = timestamp
        dbc.session.add(database.Portal().from_iitc(**portal))

    dbc.session.commit()

    return 0


def expunge(args: argparse.Namespace) -> int:
    """(V) Remove portals listed in a bookmarks file from the database."""
    dbc = args.dbc
    portals = load(args.bookmarks)
    for db_portal in dbc.session.query(database.Portal).filter(
            database.Portal.guid.in_(portals)):
        print('Deleting', db_portal.label, db_portal.last_seen)
        dbc.session.delete(db_portal)

    dbc.session.commit()

    return 0


def export(args: argparse.Namespace) -> int:
    """(V) Export all portals as a bookmarks file."""
    dbc = args.dbc
    if args.samples is None:
        guids = set(
            result[0] for result in dbc.session.query(database.Portal.guid))
        save_from_guids(guids, args.bookmarks, dbc)
    else:
        hull = dbc.session.query(
            database.geoalchemy2.functions.ST_ConvexHull(
                database.geoalchemy2.functions.ST_Union(
                    database.Portal.latlng))).scalar_subquery()
        result = dbc.session.query(database.Portal.guid).filter(
            database.geoalchemy2.functions.ST_Touches(
                hull, database.Portal.latlng))
        guids = set(row._mapping['guid'] for row in result)
        limit = max(len(guids), args.samples)
        count = limit - len(guids)
        result = dbc.session.query(database.Portal.guid).filter(
            database.Portal.guid.not_in(guids)).order_by(
                database.Portal.guid).limit(count)
        guids.update(row._mapping['guid'] for row in result)
        save_from_guids(guids, args.bookmarks, dbc)
    return 0


def flatten(args: argparse.Namespace) -> int:
    """(V) Load portals from BOOKMARKS and write out as lists using PATTERN."""
    portals = load(args.bookmarks)
    json.save_by_size(list(portals.values()), args.size, args.pattern)

    return 0


def load(filename):
    """Load a particular bookmarks file returning a dict of portals."""
    bookmarks = json.load(filename)
    portals_by_folder = bookmarks['portals']
    portals = dict()
    for folder in list(portals_by_folder.values()):
        portals_in_folder = folder['bkmrk']
        for portal in list(portals_in_folder.values()):
            guid = portal['guid']
            portals[guid] = portal

    logging.info('%s portals loaded', len(portals))
    return portals


def save(portals, filename):
    """Save a dictionary of portals into a particular bookmarks file."""
    new_bookmarks = new()
    new_bookmarks['portals']['idOthers']['bkmrk'] = portals
    json.save(filename, new_bookmarks)


def save_from_guids(guids, filename, dbc):
    """Save portals specified by guids into a particular bookmarks file."""
    portals = dict()
    for db_portal in dbc.session.query(database.Portal).filter(
            database.Portal.guid.in_(guids)):
        portals[db_portal.guid] = db_portal.to_iitc()
    save(portals, filename)


def find_missing_labels(args: argparse.Namespace) -> int:
    """(V) Look through globs of bookmarks for missing labels.

    It will remove portals with missing labels from the bookmarks and
    add them to a newly created bookmarks file instead.  The contents of
    the destination bookmarks file will be destroyed.
    """
    missing_portals: dict[str, dict] = dict()
    save(missing_portals, args.bookmarks)
    for filename in itertools.chain(*args.glob):
        missing_guids = set()
        portals = load(filename)
        for portal in list(portals.values()):
            if 'label' not in portal:
                missing_guids.add(portal['guid'])
        if missing_guids:
            for guid in missing_guids:
                missing_portals[guid] = portals[guid]
                del portals[guid]
            save(missing_portals, args.bookmarks)
            ftime = os.stat(filename)
            save(portals, filename)
            os.utime(filename, (ftime.st_atime, ftime.st_mtime))
    print(f'Portals missing labels: {len(missing_portals)}')

    return 0


def merge(args: argparse.Namespace) -> int:
    """(V) Merge multiple bookmarks files into one.

    Inputs will be the files specified by the glob arguments.  The
    contents of the destination bookmarks file will be destroyed.
    """
    portals: dict[str, dict] = dict()
    save(portals, args.bookmarks)
    for filename in itertools.chain(*args.glob):
        portals.update(load(filename))

    save(portals, args.bookmarks)

    return 0


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
