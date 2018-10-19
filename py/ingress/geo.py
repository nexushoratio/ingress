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
    _update_directions(dbc, portals)


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


def _update_directions(dbc, portals):
    now = time.time()
    for begin_portal in portals.itervalues():
        for end_portal in portals.itervalues():
            if begin_portal['guid'] != end_portal['guid']:
                for mode in ('walking', 'driving'):
                    rows = dbc.session.query(database.Path).filter(
                        database.Path.begin_latlng == begin_portal['latlng'],
                        database.Path.end_latlng == end_portal['latlng'],
                        database.Path.mode == mode)
                    if not dbc.session.query(rows.exists()).scalar():
                        db_path = database.Path(
                            begin_latlng=begin_portal['latlng'],
                            end_latlng=end_portal['latlng'],
                            mode=mode,
                            date=now)
                        dbc.session.add(db_path)
    dbc.session.commit()


def _clean(dbc):
    now = time.time()
    oldest_allowed = now - MAX_AGE
    rows = dbc.session.query(database.Address).filter(
        database.Address.date < oldest_allowed)
    for row in rows:
        print 'Delete ', row
    rows = dbc.session.query(database.Leg).filter(
        database.Leg.date < oldest_allowed)
    for row in rows:
        print 'Delete ', row
    rows = dbc.session.query(database.Path).filter(
        database.Path.date < oldest_allowed)
    for row in rows:
        print 'Delete ', row
    dbc.session.commit()
