"""Functions to work with IITC bookmarks files."""

import logging
import os

from ingress import database
from ingress import json
from ingress import zcta as zcta_lib


def import_bookmarks(args, dbc):
    """Update the portals database from a new set of bookmarks."""
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
        row.update(**portal)
        keys.remove(guid)

    # whatever is left is a new portal
    for key in keys:
        portal = portals[key]
        db_portal = database.Portal(first_seen=timestamp, **portal)
        dbc.session.add(db_portal)

    dbc.session.commit()


def load(filename):
    """Load a particular bookmarks file."""
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
