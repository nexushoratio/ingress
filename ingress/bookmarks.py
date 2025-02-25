"""Functions to work with IITC bookmarks files."""

# pylint: disable=too-many-lines

from __future__ import annotations

import enum
import functools
import glob
import itertools
import logging
import os
import pathlib
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

OTHERS = 'idOthers'

# Sentinel for a bookmark default.
DEFAULT_FOLDER = object()


class ExistingFolder(enum.StrEnum):
    """Indicates how existing folders are handled."""
    FAIL = enum.auto()
    CLEAR = enum.auto()
    APPEND = enum.auto()


def mundane_shared_flags(ctx: app.ArgparseApp):
    """Register shared flags."""
    bm_args = ('-b', '--bookmarks')
    bm_kwargs: app.AddArgumentKwargs = {
        'action': 'store',
        'help': 'IITC bookmarks json file to use.',
    }
    parser = ctx.safe_new_shared_parser('bookmarks')
    parser.add_argument(*bm_args, required=True, **bm_kwargs)

    parser = ctx.safe_new_shared_parser('bookmarks_optional')
    parser.add_argument(*bm_args, **bm_kwargs)

    existing = tuple(ExistingFolder)
    parser = ctx.safe_new_shared_parser('bookmark_label')
    parser.add_argument(
        '-b',
        '--bookmark',
        nargs=ctx.argparse_api.OPTIONAL,
        const=DEFAULT_FOLDER,
        action='store',
        metavar='LABEL',
        help=(
            'Enable use of a bookmark folder.  Depending on context, the'
            ' value in LABEL may be used.'
        )
    )
    parser.add_argument(
        '--existing-mode',
        action='store',
        default=existing[0],
        choices=existing,
        help=(
            'Control how existing folders should be treated when the'
            ' bookmark folder feature is enabled.  (Default: %(default)s)'
        )
    )

    parser = ctx.safe_new_shared_parser('folder_id_req')
    parser.add_argument(
        '--folder-id',
        action='store',
        required=True,
        help='Folder UUID to use.'
    )

    parser = ctx.safe_new_shared_parser('folder_id_req_list')
    parser.add_argument(
        '-f',
        '--folder-id',
        action='append',
        required=True,
        help='Folder UUID to use.  May be specified multiple times.'
    )

    parser = ctx.safe_new_shared_parser('glob')
    parser.add_argument(
        '-g',
        '--glob',
        action='append',
        required=True,
        type=glob.iglob,  # type: ignore[arg-type]  # old version of mypy
        help=(
            'A filename glob that will be matched by the program'
            ' instead of the shell.  May be specified multiple times.'
        )
    )


class _CommonFlags:
    """A module level container for flags used across multiple commands."""

    def __init__(self, ctx: app.ArgparseApp):
        """Initialize the container.

        Args:
            ctx: The ArgparseApp instance to use.
        """
        self._ctx = ctx

    def _parser(self) -> argparse.ArgumentParser:
        return self._ctx.new_parser()

    @functools.cached_property
    def folder_id_req(self) -> argparse.ArgumentParser:
        """Required --folder-id flag."""
        return self._ctx.safe_get_shared_parser('folder_id_req')

    @functools.cached_property
    def folder_id_opt(self) -> argparse.ArgumentParser:
        """Optional --folder-id flag."""
        parser = self._parser()
        parser.add_argument(
            '--folder-id', action='store', help='Folder UUID to use.'
        )
        return parser

    @functools.cached_property
    def folder_id_req_list(self) -> argparse.ArgumentParser:
        """Required repeatable --folder-id flag."""
        return self._ctx.safe_get_shared_parser('folder_id_req_list')

    @functools.cached_property
    def label_req(self) -> argparse.ArgumentParser:
        """Required --label flag."""
        parser = self._parser()
        parser.add_argument(
            '--label', action='store', required=True, help='Label to use.'
        )
        return parser

    @functools.cached_property
    def label_opt(self) -> argparse.ArgumentParser:
        """Optional --label flag."""
        parser = self._parser()
        parser.add_argument('--label', action='store', help='Label to use.')
        return parser

    @functools.cached_property
    def latlng_req(self) -> argparse.ArgumentParser:
        """Required --latlng flag."""
        parser = self._parser()
        parser.add_argument(
            '--latlng',
            action='store',
            required=True,
            help='Latitude/longitude value to use.'
        )
        return parser

    @functools.cached_property
    def latlng_opt(self) -> argparse.ArgumentParser:
        """Optional --latlng flag."""
        parser = self._parser()
        parser.add_argument(
            '--latlng',
            action='store',
            help='Latitude/longitude value to use.'
        )
        return parser

    @functools.cached_property
    def note_opt(self) -> argparse.ArgumentParser:
        """Optional --note flag."""
        parser = self._parser()
        parser.add_argument(
            '--note', action='store', help='Optional note to use.'
        )
        return parser

    @functools.cached_property
    def place_id_req(self) -> argparse.ArgumentParser:
        """Required --place-id flag."""
        parser = self._parser()
        parser.add_argument(
            '--place-id',
            action='store',
            required=True,
            help='Place UUID to use.'
        )
        return parser

    @functools.cached_property
    def place_id_opt(self) -> argparse.ArgumentParser:
        """Optional --place-id flag."""
        parser = self._parser()
        parser.add_argument(
            '--place-id', action='store', help='Place UUID to use.'
        )
        return parser

    @functools.cached_property
    def portal_id_req(self) -> argparse.ArgumentParser:
        """Required --portal-id flag."""
        parser = self._parser()
        parser.add_argument(
            '--portal-id',
            action='store',
            required=True,
            help='Portal GUID to use.'
        )
        return parser

    @functools.cached_property
    def portal_id_opt(self) -> argparse.ArgumentParser:
        """Optional --portal-id flag."""
        parser = self._parser()
        parser.add_argument(
            '--portal-id', action='store', help='Portal GUID to use.'
        )
        return parser

    @functools.cached_property
    def uuid_req(self) -> argparse.ArgumentParser:
        """Required --uuid flag."""
        parser = self._parser()
        parser.add_argument(
            '--uuid', action='store', required=True, help='UUID to use.'
        )
        return parser

    @functools.cached_property
    def uuid_req_list(self) -> argparse.ArgumentParser:
        """Required repeatable --uuid flag."""
        parser = self._parser()
        parser.add_argument(
            '-u',
            '--uuid',
            action='append',
            required=True,
            help='UUID to use.  May be specified multiple times.'
        )
        return parser

    @functools.cached_property
    def uuid_opt(self) -> argparse.ArgumentParser:
        """Optional --uuid flag."""
        parser = self._parser()
        parser.add_argument('--uuid', action='store', help='UUID to use.')
        return parser

    @functools.cached_property
    def zoom_req(self) -> argparse.ArgumentParser:
        """Required --zoom flag."""
        parser = self._parser()
        parser.add_argument(
            '--zoom',
            action='store',
            required=True,
            type=int,
            help='Zoom level to use.'
        )
        return parser

    @functools.cached_property
    def zoom_opt(self) -> argparse.ArgumentParser:
        """Optional --zoom flag."""
        parser = self._parser()
        parser.add_argument(
            '--zoom', action='store', type=int, help='Zoom level to use.'
        )
        return parser


def mundane_commands(ctx: app.ArgparseApp):
    """Register commands."""
    bm_flags = ctx.safe_get_shared_parser('bookmarks')
    glob_flags = ctx.safe_get_shared_parser('glob')

    parser = ctx.register_command(flatten, parents=[bm_flags])
    parser.add_argument(
        '-s',
        '--size',
        action='store',
        default=3 * 1024 * 1024,
        type=int,
        help=(
            'Rough upper limit on the size (in bytes) of each flattened'
            ' output file.  (Default: %(default)s)'
        )
    )
    parser.add_argument(
        '-p',
        '--pattern',
        action='store',
        default='flattened-{size}-{count:0{width}d}.json',
        help=(
            'Pattern used to name the output files.  Uses PEP 3101'
            ' formatting strings with the following fields:  size,'
            ' width, count.  (Default: %(default)s)'
        )
    )

    ctx.register_command(find_missing_labels, parents=[bm_flags, glob_flags])
    ctx.register_command(merge, parents=[bm_flags, glob_flags])

    flags = _CommonFlags(ctx)

    bookmark_cmds = ctx.new_subparser(
        ctx.register_command(_bookmark, name='bookmark', usage_only=True)
    )

    ctx.register_command(
        read_, name='read', subparser=bookmark_cmds, parents=[bm_flags]
    )
    ctx.register_command(
        write_,
        name='write',
        subparser=bookmark_cmds,
        parents=[bm_flags, flags.folder_id_req_list]
    )

    folder_cmds = ctx.new_subparser(
        ctx.register_command(
            _folder, name='folder', usage_only=True, subparser=bookmark_cmds
        )
    )

    ctx.register_command(folder_list, name='list', subparser=folder_cmds)
    ctx.register_command(
        folder_add,
        name='add',
        subparser=folder_cmds,
        parents=[flags.uuid_opt, flags.label_req]
    )
    ctx.register_command(
        folder_set,
        name='set',
        subparser=folder_cmds,
        parents=[flags.uuid_req, flags.label_opt]
    )
    ctx.register_command(
        folder_clear,
        name='clear',
        subparser=folder_cmds,
        parents=[flags.uuid_req]
    )
    ctx.register_command(
        folder_del,
        name='del',
        subparser=folder_cmds,
        parents=[flags.uuid_req_list]
    )

    place_cmds = ctx.new_subparser(
        ctx.register_command(_place, name='place', usage_only=True)
    )

    ctx.register_command(place_list, name='list', subparser=place_cmds)
    ctx.register_command(
        place_add,
        name='add',
        subparser=place_cmds,
        parents=[flags.label_req, flags.latlng_req, flags.note_opt]
    )
    ctx.register_command(
        place_set,
        name='set',
        subparser=place_cmds,
        parents=[
            flags.uuid_req, flags.label_opt, flags.latlng_opt, flags.note_opt
        ]
    )
    ctx.register_command(
        place_del,
        name='del',
        subparser=place_cmds,
        parents=[flags.uuid_req_list]
    )

    map_cmds = ctx.new_subparser(
        ctx.register_command(
            _map, name='map', usage_only=True, subparser=bookmark_cmds
        )
    )

    ctx.register_command(map_list, name='list', subparser=map_cmds)
    ctx.register_command(
        map_add,
        name='add',
        subparser=map_cmds,
        parents=[flags.folder_id_req, flags.place_id_req, flags.zoom_req]
    )
    ctx.register_command(
        map_set,
        name='set',
        subparser=map_cmds,
        parents=[
            flags.uuid_req, flags.folder_id_opt, flags.place_id_opt,
            flags.zoom_opt
        ]
    )
    ctx.register_command(
        map_del,
        name='del',
        subparser=map_cmds,
        parents=[flags.uuid_req_list]
    )

    portal_cmds = ctx.new_subparser(
        ctx.register_command(
            _portal, name='portal', usage_only=True, subparser=bookmark_cmds
        )
    )

    ctx.register_command(portal_list, name='list', subparser=portal_cmds)
    ctx.register_command(
        portal_add,
        name='add',
        subparser=portal_cmds,
        parents=[flags.folder_id_req, flags.portal_id_req]
    )
    ctx.register_command(
        portal_set,
        name='set',
        subparser=portal_cmds,
        parents=[flags.uuid_req, flags.folder_id_opt, flags.portal_id_opt]
    )
    ctx.register_command(
        portal_del,
        name='del',
        subparser=portal_cmds,
        parents=[flags.uuid_req_list]
    )


def _place(args: argparse.Namespace) -> int:
    """(V) A family of commands for working with places."""
    raise Error('This function should never be called.')


def _bookmark(args: argparse.Namespace) -> int:
    """(V) A family of commands for working with bookmarks in the database."""
    raise Error('This function should never be called.')


def _folder(args: argparse.Namespace) -> int:
    """(V) A family of commands for working with bookmark folders."""
    raise Error('This function should never be called.')


def _map(args: argparse.Namespace) -> int:
    """(V) A family of commands for working with map bookmarks.

    A map bookmark consists of a (folder, place, zoom) combination.
    """
    raise Error('This function should never be called.')


def _portal(args: argparse.Namespace) -> int:
    """(V) A family of commands for working with portal bookmarks.

    A portal bookmark consists of a (folder, portal) combination.
    """
    raise Error('This function should never be called.')


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

    stmt = sqla.select(database.PortalV2
                       ).where(database.PortalV2.guid.in_(guids))

    for row in dbc.session.execute(stmt):
        portal = row.PortalV2
        portals[portal.guid] = portal.to_iitc()
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
            f' | {row.BookmarkFolder.label}'
        )

    return 0


def folder_add(args: argparse.Namespace) -> int:
    """(V) Add a new bookmark folder to the database."""
    dbc = args.dbc

    folder = database.BookmarkFolder(label=args.label)
    if args.uuid:
        folder.uuid = args.uuid
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


def folder_clear(args: argparse.Namespace) -> int:
    """(V) Clear all entries in a bookmark folder from the database."""
    dbc = args.dbc

    folder = dbc.session.get(database.BookmarkFolder, args.uuid)
    ret = 0
    if folder:
        _clear_folder(dbc, folder)
        dbc.session.commit()
    else:
        print(f'Unknown uuid: "{args.uuid}"')
        ret = 1

    return ret


def folder_del(args: argparse.Namespace) -> int:
    """(V) Delete one or more bookmark folders from the database."""

    return _delete_by_uuids(args.dbc, database.BookmarkFolder, args.uuid)


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
        f' | {latlng_col_header:^{latlng_col_width}} | Note'
    )
    for row in dbc.session.execute(stmt):
        print(
            f'{row.Place.uuid:{uuid_col_width}}'
            f' | {row.Place.label:{label_col_width}}'
            f' |{row.Place.lat:>{lng_col_width}}'
            f',{row.Place.lng:<{lng_col_width}}'
            f' | {row.Place.note if row.Place.note else "~~"}'
        )

    return 0


def place_add(args: argparse.Namespace) -> int:
    """(V) Add a specific place to the database."""
    dbc = args.dbc

    place = database.Place(
        label=args.label, latlng=args.latlng, note=args.note
    )
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


def place_del(args: argparse.Namespace) -> int:
    """(V) Delete one or more specific places from the database."""

    return _delete_by_uuids(args.dbc, database.Place, args.uuid)


def map_list(args: argparse.Namespace) -> int:
    """(V) List existing map bookmarks in the database.

    This report is really wide.  Sorry.
    """
    dbc = args.dbc

    stmt = sqla.select(database.MapBookmark)

    uuid_col_header = 'UUID'
    folder_col_header = 'Folder (label - uuid)'
    place_col_header = 'Place (label - uuid)'
    uuid_col_width = 32
    # consisent with place_list
    label_width = 14
    wide_col_width = uuid_col_width + label_width + 3
    print(
        f'{uuid_col_header:^{uuid_col_width}}'
        f' | {folder_col_header:^{wide_col_width}}'
        f' | {place_col_header:^{wide_col_width}}'
        ' | Zoom'
    )
    for row in dbc.session.execute(stmt):
        this_folder = dbc.session.get(
            database.BookmarkFolder, row.MapBookmark.folder_id
        )
        this_place = dbc.session.get(database.Place, row.MapBookmark.place_id)
        print(
            f'{row.MapBookmark.uuid:{uuid_col_width}}'
            f' | {this_folder.label:{label_width}}'
            f' - {this_folder.uuid:{uuid_col_width}}'
            f' | {this_place.label:{label_width}}'
            f' - {this_place.uuid:{uuid_col_width}}'
            f' | {row.MapBookmark.zoom}'
        )

    return 0


def map_add(args: argparse.Namespace) -> int:
    """(V) Add a new map bookmark to the database."""
    dbc = args.dbc

    this_map = database.MapBookmark(
        folder_id=args.folder_id, place_id=args.place_id, zoom=args.zoom
    )
    dbc.session.add(this_map)
    dbc.session.commit()

    return 0


def map_set(args: argparse.Namespace) -> int:
    """(V) Update settings on a map bookmark in the database."""
    dbc = args.dbc

    this_map = dbc.session.get(database.MapBookmark, args.uuid)
    ret = 0
    if this_map:
        if args.folder_id:
            this_map.folder_id = args.folder_id
        if args.place_id:
            this_map.place_id = args.place_id
        if args.zoom:
            this_map.zoom = args.zoom
        dbc.session.add(this_map)
        dbc.session.commit()
    else:
        print(f'Unknown uuid: "{args.uuid}"')
        ret = 1

    return ret


def map_del(args: argparse.Namespace) -> int:
    """(V) Delete one or more map bookmarks from the database."""

    return _delete_by_uuids(args.dbc, database.MapBookmark, args.uuid)


def portal_list(args: argparse.Namespace) -> int:
    """(V) List existing portal bookmarks in the database.

    This report is really wide.  Sorry.
    """
    dbc = args.dbc

    stmt = sqla.select(database.PortalBookmark)

    uuid_col_header = 'UUID'
    folder_col_header = 'Folder (label - uuid)'
    portal_col_header = 'Portal (label - uuid)'
    uuid_col_width = 32
    guid_col_width = 35
    # consisent with place_list
    label_width = 14
    # About 80% of the portals are less than this
    portal_label_width = 34
    folder_col_width = uuid_col_width + label_width + 3
    portal_col_width = guid_col_width + portal_label_width + 3
    print(
        f'{uuid_col_header:^{uuid_col_width}}'
        f' | {folder_col_header:^{folder_col_width}}'
        f' | {portal_col_header:^{portal_col_width}}'
    )

    for row in dbc.session.execute(stmt):
        this_folder = dbc.session.get(
            database.BookmarkFolder, row.PortalBookmark.folder_id
        )
        this_portal = dbc.session.get(
            database.PortalV2, row.PortalBookmark.portal_id
        )
        print(
            f'{row.PortalBookmark.uuid:{uuid_col_width}}'
            f' | {this_folder.label:{label_width}}'
            f' - {this_folder.uuid:{uuid_col_width}}'
            f' | {this_portal.label:{portal_label_width}}'
            f' - {this_portal.guid:{guid_col_width}}'
        )

    return 0


def portal_add(args: argparse.Namespace) -> int:
    """(V) Add a new portal bookmark to the database."""
    dbc = args.dbc

    this_portal = database.PortalBookmark(
        folder_id=args.folder_id, portal_id=args.portal_id
    )
    dbc.session.add(this_portal)
    dbc.session.commit()

    return 0


def portal_set(args: argparse.Namespace) -> int:
    """(V) Update settings on a portal bookmark in the database."""
    dbc = args.dbc

    this_portal = dbc.session.get(database.PortalBookmark, args.uuid)
    ret = 0
    if this_portal:
        if args.folder_id:
            this_portal.folder_id = args.folder_id
        if args.portal_id:
            this_portal.portal_id = args.portal_id
        if args.zoom:
            this_portal.zoom = args.zoom
        dbc.session.add(this_portal)
        dbc.session.commit()
    else:
        print(f'Unknown uuid: "{args.uuid}"')
        ret = 1

    return ret


def portal_del(args: argparse.Namespace) -> int:
    """(V) Delete one more more portal bookmarks from the database."""

    return _delete_by_uuids(args.dbc, database.PortalBookmark, args.uuid)


def read_(args: argparse.Namespace) -> int:
    """(V) Read an IITC style bookmark file.

    This will import the bookmark file to populate the internal bookmark
    tables.

    Folders and places will be populated automatically.

    Any portals not already ingested will be skipped with a notification.

    Hint: See the other "bookmark" family of commands for additional
    processing.
    """
    dbc = args.dbc

    filename = pathlib.PurePath(args.bookmarks).stem
    bookmarks = json.load(args.bookmarks)

    for section, value in bookmarks.items():
        if section == 'maps':
            _process_maps(dbc, filename, value)
        elif section == 'portals':
            _process_portals(dbc, filename, value)
        else:
            print(f'Unknown section: {section}')

    dbc.session.commit()

    return 0


def _process_maps(
    dbc: database.Database, other: str, value: dict[str, typing.Any]
):
    """Process the map bookmarks."""
    for folder_id, folder_value in value.items():
        folder_label = folder_value['label']
        maps = folder_value['bkmrk']
        if folder_id == OTHERS:
            folder_id = other
            folder_label = other
        folder = database.BookmarkFolder(uuid=folder_id, label=folder_label)
        dbc.session.merge(folder)
        for map_id, map_value in maps.items():
            label = map_value['label']
            latlng = map_value['latlng']
            zoom = map_value['z']
            place = database.Place(uuid=map_id, label=label, latlng=latlng)
            dbc.session.merge(place)
            this_map = database.MapBookmark(
                uuid=map_id, folder_id=folder_id, place_id=map_id, zoom=zoom
            )
            dbc.session.merge(this_map)


def _process_portals(
    dbc: database.Database, other: str, value: dict[str, typing.Any]
):
    """Process the portal bookmarks."""
    for folder_id, folder_value in value.items():
        folder_label = folder_value['label']
        portals = folder_value['bkmrk']
        if folder_id == OTHERS:
            folder_id = other
            folder_label = other
        folder = database.BookmarkFolder(uuid=folder_id, label=folder_label)
        dbc.session.merge(folder)
        for bm_id, portal_value in portals.items():
            guid = portal_value['guid']
            portal = dbc.session.get(database.PortalV2, guid)
            if portal is None:
                print('Skipping', portal_value)
            else:
                this_portal = database.PortalBookmark(
                    uuid=bm_id, folder_id=folder_id, portal_id=guid
                )
                dbc.session.merge(this_portal)


def write_(args: argparse.Namespace) -> int:
    """(V) Write an IITC style bookmark file.

    This will create a file populated with the maps and portals listed in the
    requested folders.

    Hint: See the other "bookmark" family of commands for creating and tuning
    the contents of such bookmarks.
    """
    dbc = args.dbc

    bookmarks = new()

    ret = 0
    for folder_id in args.folder_id:
        folder = dbc.session.get(database.BookmarkFolder, folder_id)
        if folder:
            maps = dict()
            portals = dict()

            stmt = sqla.select(database.MapBookmark, database.Place).join(
                database.Place,
                database.MapBookmark.place_id == database.Place.uuid
            ).where(database.MapBookmark.folder_id == folder_id)

            for row in dbc.session.execute(stmt).mappings():
                bkmrk = row['MapBookmark']
                place = row['Place']
                maps[bkmrk.uuid] = {
                    'label': place.label,
                    'latlng': place.latlng,
                    'z': bkmrk.zoom,
                }
            if maps:
                bookmarks['maps'][folder_id] = {
                    'bkmrk': maps,
                    'label': folder.label,
                }

            stmt = sqla.select(
                database.PortalBookmark, database.PortalV2
            ).join(
                database.PortalV2,
                database.PortalBookmark.portal_id == database.PortalV2.guid
            ).where(database.PortalBookmark.folder_id == folder_id)

            for row in dbc.session.execute(stmt).mappings():
                bkmrk = row['PortalBookmark']
                portal = row['PortalV2']
                portals[bkmrk.uuid] = portal.to_iitc()
            if portals:
                bookmarks['portals'][folder_id] = {
                    'bkmrk': portals,
                    'label': folder.label,
                }
        else:
            print(f'Unknown folder id: "{folder_id}"')
            ret = 1
            break

    if not ret:
        json.save(args.bookmarks, bookmarks)

    return ret


def prepare_folder(
    dbc: database.Database, label: str, existing: ExistingFolder
) -> database.BookmarkFolder:
    """Prepare a folder based upon the supplied parameters.

    It will be flushed to the database.
    """
    stmt = sqla.select(database.BookmarkFolder
                       ).where(database.BookmarkFolder.label == label)
    old_folder = dbc.session.scalar(stmt)
    # Using an older version of yapf that does not support match/case.
    if old_folder and existing == ExistingFolder.FAIL:
        raise Error(f'The bookmark folder "{label}" already exists.')
    if old_folder and existing == ExistingFolder.CLEAR:
        folder = _clear_folder(dbc, old_folder)
    elif old_folder and existing == ExistingFolder.APPEND:
        folder = old_folder
    else:
        folder = database.BookmarkFolder(label=label)
        dbc.session.add(folder)
        dbc.session.flush([folder])

    return folder


def _clear_folder(
    dbc: database.Database, folder: database.BookmarkFolder
) -> database.BookmarkFolder:
    """Clear references to a bookmark folder."""
    inputs = dict(
        (key, getattr(folder, key)) for key in folder.__mapper__.c.keys()
    )
    dbc.session.delete(folder)
    dbc.session.flush()
    new_folder = database.BookmarkFolder(**inputs)
    dbc.session.add(new_folder)
    dbc.session.flush([new_folder])
    return new_folder


def _delete_by_uuids(dbc: database.Database, table, uuids: list[str]) -> int:
    """Delete items from the specified table based upon UUIDs."""
    ret = 0

    for uuid in uuids:
        item = dbc.session.get(table, uuid)
        if item:
            dbc.session.delete(item)
        else:
            print(f'Unknown uuid: "{uuid}"')
            ret = 1

    if ret:
        dbc.session.rollback()
    else:
        dbc.session.commit()

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
