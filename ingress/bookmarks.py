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


class Error(Exception):
    """Base module exception."""


Portals: typing.TypeAlias = dict[str, database.PortalDict]

sqla = database.sqlalchemy


def mundane_shared_flags(ctx: app.ArgparseApp):
    """Register shared flags."""
    bm_args = ('-b', '--bookmarks')
    bm_kwargs: app.AddArgumentKwargs = {
        'action': 'store',
        'help': 'IITC bookmarks json file to use.',
    }
    parser = ctx.new_shared_parser('bookmarks')
    if parser:
        parser.add_argument(*bm_args, required=True, **bm_kwargs)

    parser = ctx.new_shared_parser('bookmarks_optional')
    if parser:
        parser.add_argument(*bm_args, **bm_kwargs)

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

    ctx.register_command(
        export, parents=[bm_flags]).add_argument(
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
        help=(
            'Rough upper limit on the size (in bytes) of each flattened'
            ' output file.  (Default: %(default)s)'))
    parser.add_argument(
        '-p',
        '--pattern',
        action='store',
        default='flattened-{size}-{count:0{width}d}.json',
        help=(
            'Pattern used to name the output files.  Uses PEP 3101'
            ' formatting strings with the following fields:  size,'
            ' width, count.  (Default: %(default)s)'))

    ctx.register_command(find_missing_labels, parents=[bm_flags, glob_flags])
    ctx.register_command(merge, parents=[bm_flags, glob_flags])

    label_req_flag = ctx.argparse_api.ArgumentParser(add_help=False)
    label_req_flag.add_argument(
        '--label', action='store', required=True, help='Label to use.')
    label_opt_flag = ctx.argparse_api.ArgumentParser(add_help=False)
    label_opt_flag.add_argument(
        '--label', action='store', help='Label to use.')

    uuid_req_flag = ctx.argparse_api.ArgumentParser(add_help=False)
    uuid_req_flag.add_argument(
        '--uuid', action='store', required=True, help='UUID to use.')

    latlng_req_flag = ctx.argparse_api.ArgumentParser(add_help=False)
    latlng_req_flag.add_argument(
        '--latlng',
        action='store',
        required=True,
        help='Latitude/longitude value to use.')

    latlng_opt_flag = ctx.argparse_api.ArgumentParser(add_help=False)
    latlng_opt_flag.add_argument(
        '--latlng', action='store', help='Latitude/longitude value to use.')

    note_opt_flag = ctx.argparse_api.ArgumentParser(add_help=False)
    note_opt_flag.add_argument(
        '--note', action='store', help='Optional note to add')

    bookmark_cmds = ctx.new_subparser(
        ctx.register_command(bookmark, usage_only=True))

    folder_cmds = ctx.new_subparser(
        ctx.register_command(
            folder_, name='folder', usage_only=True, subparser=bookmark_cmds))

    ctx.register_command(folder_list, name='list', subparser=folder_cmds)
    ctx.register_command(
        folder_add,
        name='add',
        subparser=folder_cmds,
        parents=[label_req_flag])
    ctx.register_command(
        folder_set,
        name='set',
        subparser=folder_cmds,
        parents=[uuid_req_flag, label_opt_flag])
    ctx.register_command(
        folder_del,
        name='del',
        subparser=folder_cmds,
        parents=[uuid_req_flag])

    place_cmds = ctx.new_subparser(
        ctx.register_command(place_holder, name='place', usage_only=True))

    ctx.register_command(place_list, name='list', subparser=place_cmds)
    ctx.register_command(
        place_add,
        name='add',
        subparser=place_cmds,
        parents=[label_req_flag, latlng_req_flag, note_opt_flag])
    ctx.register_command(
        place_set,
        name='set',
        subparser=place_cmds,
        parents=[
            uuid_req_flag, label_opt_flag, latlng_opt_flag, note_opt_flag
        ])
    ctx.register_command(
        place_delete,
        name='del',
        subparser=place_cmds,
        parents=[uuid_req_flag])


def place_holder(args: argparse.Namespace) -> int:
    """(V) A family of commands for working with places."""
    raise Error('This function should never be called.')


def bookmark(args: argparse.Namespace) -> int:
    """(V) A family of commands for working with bookmarks in the database."""
    raise Error('This function should never be called.')


def folder_(args: argparse.Namespace) -> int:
    """(V) A family of commands for working with bookmark folders."""
    raise Error('This function should never be called.')


def ingest(args: argparse.Namespace) -> int:
    """(V) Update the database with portals listed in a bookmarks file.

    Hint: Use the 'address-update' command after this to populate address
    related information.
    """
    dbc = args.dbc
    portals = load(args.bookmarks)
    timestamp = int(os.stat(args.bookmarks).st_mtime)

    # Of all of the variations I tried for doing these updates, this algorithm
    # is the fastest.  At some point, the data may be too large for the `in_`
    # query, but by that point, it is likely that the bookmarks could not be
    # loaded into memory either.
    for portal in portals.values():
        portal['last_seen'] = timestamp

    # Look for existing portals first
    rows = dbc.session.query(database.PortalV2).filter(
        database.PortalV2.guid.in_(portals))
    for row in rows:
        guid = row.guid
        portal = portals[guid]
        # only update if newer
        if portal['last_seen'] > row.last_seen:
            dbc.session.merge(database.PortalV2(**portal))

        del portals[guid]

    # Whatever is left is a new portal
    for portal in portals.values():
        portal['first_seen'] = timestamp
        dbc.session.add(database.PortalV2(**portal))

    dbc.session.commit()

    return 0


def expunge(args: argparse.Namespace) -> int:
    """(V) Remove portals listed in a bookmarks file from the database."""
    dbc = args.dbc
    portals = load(args.bookmarks)
    for db_portal in dbc.session.query(database.PortalV2).filter(
            database.PortalV2.guid.in_(portals)):
        print('Deleting', db_portal.label, db_portal.last_seen)
        dbc.session.delete(db_portal)

    dbc.session.commit()

    return 0


def export(args: argparse.Namespace) -> int:
    """(V) Export all portals as a bookmarks file."""
    dbc = args.dbc
    if args.samples is None:
        guids = set(
            result[0] for result in dbc.session.query(database.PortalV2.guid))
        save_from_guids(guids, args.bookmarks, dbc)
    else:
        hull = dbc.session.query(
            database.geoalchemy2.functions.ST_ConvexHull(
                database.geoalchemy2.functions.ST_Union(
                    database.PortalV2.point))).scalar_subquery()
        result = dbc.session.query(database.PortalV2.guid).filter(
            database.geoalchemy2.functions.ST_Touches(
                hull, database.PortalV2.point))
        guids = set(row._mapping['guid'] for row in result)
        limit = max(len(guids), args.samples)
        count = limit - len(guids)
        result = dbc.session.query(database.PortalV2.guid).filter(
            database.PortalV2.guid.not_in(guids)).order_by(
                database.PortalV2.guid).limit(count)
        guids.update(row._mapping['guid'] for row in result)
        save_from_guids(guids, args.bookmarks, dbc)
    return 0


def flatten(args: argparse.Namespace) -> int:
    """(V) Load portals from BOOKMARKS and save flat lists using PATTERN."""
    portals = load(args.bookmarks)
    json.save_by_size(list(portals.values()), args.size, args.pattern)

    return 0


def load(filename: str) -> Portals:
    """Load a particular bookmarks file returning a dict of portals."""
    bookmarks = json.load(filename)
    portals_by_folder = bookmarks['portals']
    portals: Portals = dict()
    for folder in list(portals_by_folder.values()):
        portals_in_folder = folder['bkmrk']
        for portal in list(portals_in_folder.values()):
            guid = portal['guid']
            portals[guid] = portal

    logging.info('%s portals loaded', len(portals))
    return portals


def save(portals: Portals, filename: str):
    """Save a dictionary of portals into a particular bookmarks file."""
    new_bookmarks = new()
    new_bookmarks['portals']['idOthers']['bkmrk'] = portals
    json.save(filename, new_bookmarks)


def save_from_guids(guids, filename, dbc):
    """Save portals specified by guids into a particular bookmarks file."""
    portals = dict()
    for db_portal in dbc.session.query(database.PortalV2).filter(
            database.PortalV2.guid.in_(guids)):
        portals[db_portal.guid] = db_portal.to_iitc()
    save(portals, filename)


def find_missing_labels(args: argparse.Namespace) -> int:
    """(V) Look through globs of bookmarks for missing labels.

    It will remove portals with missing labels from the bookmarks and
    add them to a newly created bookmarks file instead.  The contents of
    the destination bookmarks file will be destroyed.
    """
    missing_portals: Portals = dict()
    save(missing_portals, args.bookmarks)
    for filename in itertools.chain(*args.glob):
        missing_guids: set[str] = set()
        portals = load(filename)
        for portal in portals.values():
            if 'label' not in portal:
                assert isinstance(portal['guid'], str)
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
    portals: Portals = dict()
    save(portals, args.bookmarks)
    for filename in itertools.chain(*args.glob):
        portals.update(load(filename))

    save(portals, args.bookmarks)

    return 0


def folder_list(args: argparse.Namespace) -> int:
    """(V) List existing bookmark folders in the database."""
    dbc = args.dbc

    stmt = sqla.select(database.BookmarkFolder)

    uuid_col_header = 'UUID'
    uuid_col_width = 32
    print(f'{uuid_col_header:^{uuid_col_width}} | Label')
    for row in dbc.session.execute(stmt):
        print(
            f'{row.BookmarkFolder.uuid:{uuid_col_width}}'
            f' | {row.BookmarkFolder.label}')

    return 0


def folder_add(args: argparse.Namespace) -> int:
    """(V) Add a new bookmark folder to the database."""
    dbc = args.dbc
    folder = database.BookmarkFolder(label=args.label)
    dbc.session.add(folder)
    dbc.session.commit()

    return 0


def folder_set(args: argparse.Namespace) -> int:
    """(V) Update settings on a bookmark folder in the database."""
    dbc = args.dbc

    folder = dbc.session.get(database.BookmarkFolder, args.uuid)
    ret = 0
    if folder:
        if args.label:
            folder.label = args.label
        dbc.session.add(folder)
        dbc.session.commit()
    else:
        print(f'Unknown uuid: "{args.uuid}"')
        ret = 1

    return ret


def folder_del(args: argparse.Namespace) -> int:
    """(V) Delete a bookmark folder from the database."""
    dbc = args.dbc

    folder = dbc.session.get(database.BookmarkFolder, args.uuid)
    ret = 0
    if folder:
        dbc.session.delete(folder)
        dbc.session.commit()
    else:
        print(f'Unknown uuid: "{args.uuid}"')
        ret = 1

    return ret


def place_list(args: argparse.Namespace) -> int:
    """(V) List specific places in the database."""
    dbc = args.dbc
    stmt = sqla.select(database.Place)

    uuid_col_header = 'UUID'
    uuid_col_width = 32
    label_col_header = 'Label'
    # 14 allows an empty note to fit on an 80 col term
    label_col_width = 14
    latlng_col_header = 'Lat/Lng'
    lat_col_width = len('-89.123456')
    lng_col_width = len('-179.123456')
    latlng_col_width = lat_col_width + lng_col_width + 1

    print(
        f'{uuid_col_header:^{uuid_col_width}}'
        f' | {label_col_header:^{label_col_width}}'
        f' | {latlng_col_header:^{latlng_col_width}} | Note')
    for row in dbc.session.execute(stmt):
        print(
            f'{row.Place.uuid:{uuid_col_width}}'
            f' | {row.Place.label:{label_col_width}}'
            f' |{row.Place.lat:>{lng_col_width}}'
            f',{row.Place.lng:<{lng_col_width}}'
            f' | {row.Place.note if row.Place.note else "~~"}')

    return 0


def place_add(args: argparse.Namespace) -> int:
    """(V) Add a specific place to the database."""
    dbc = args.dbc
    place = database.Place(
        label=args.label, latlng=args.latlng, note=args.note)
    dbc.session.add(place)
    dbc.session.commit()

    return 0


def place_set(args: argparse.Namespace) -> int:
    """(V) Update settings on a specific place in the database."""
    dbc = args.dbc

    place = dbc.session.get(database.Place, args.uuid)
    ret = 0
    if place:
        if args.label:
            place.label = args.label
        if args.latlng:
            place.latlng = args.latlng
        # note can be an empty string
        if args.note is not None:
            place.note = args.note
        dbc.session.add(place)
        dbc.session.commit()
    else:
        print(f'Unknown uuid: "{args.uuid}"')
        ret = 1

    return ret


def place_delete(args: argparse.Namespace) -> int:
    """(V) Delete a specific place from the database."""
    dbc = args.dbc
    place = dbc.session.get(database.Place, args.uuid)
    ret = 0
    if place:
        dbc.session.delete(place)
        dbc.session.commit()
    else:
        print(f'Unknown uuid: "{args.uuid}"')
        ret = 1

    return ret


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
