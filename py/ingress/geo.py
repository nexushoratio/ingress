"""Functions for all things geo related."""

import time

from ingress import database
from ingress import bookmarks
from ingress import google

MAX_AGE = 90 * 24 * 60 * 60


def update(args, dbc):
    """Update the distances between portals listed in the bookmarks."""
    portals = bookmarks.load(args.bookmarks)
    _clean(dbc)
    _update_addresses(dbc, portals)


def _update_addresses(dbc, portals):
    now = time.time()
    latlngs = [portal['latlng'] for portal in portals.itervalues()]
    for latlng in latlngs:
        rows = dbc.session.query(database.Address).filter(
            database.Address.latlng == latlng)
        if not dbc.session.query(rows.exists()).scalar():
            street_address = google.latlng_to_address(latlng)
            db_address = database.Address(
                latlng=latlng, address=street_address, date=now)
            dbc.session.add(db_address)
            dbc.session.commit()


def _clean(dbc):
    now = time.time()
    oldest_allowed = now - MAX_AGE
    rows = dbc.session.query(database.Address).filter(
        database.Address.date < oldest_allowed)
    for row in rows:
        print 'Delete ', row
