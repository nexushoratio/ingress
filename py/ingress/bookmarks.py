"""Functions to work with IITC bookmarks files."""

import logging
import os

from ingress import database
from ingress import json
from ingress import zcta as zcta_lib


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
