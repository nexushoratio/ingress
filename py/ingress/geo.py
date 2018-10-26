"""Functions for all things geo related."""

import collections
import itertools
import random
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


def _portal_combos(portals):
    for begin_portal in portals.itervalues():
        for end_portal in portals.itervalues():
            if begin_portal['guid'] != end_portal['guid']:
                for mode in ('walking', 'driving'):
                    yield begin_portal, end_portal, mode


def _grouper(iterable, size):
    args = [iter(iterable)] * size
    return itertools.izip_longest(*args)


def _update_addresses(dbc, portals):
    now = time.time()
    needed = set()
    latlng_groups = _grouper((portal['latlng']
                              for portal in portals.itervalues()), 64)
    for latlng_group in latlng_groups:
        filtered_latlng_group = [x for x in latlng_group if x is not None]
        needed.update(filtered_latlng_group)
        rows = dbc.session.query(database.Address).filter(
            database.Address.latlng.in_(filtered_latlng_group))
        have = set(row.latlng for row in rows)
        needed.difference_update(have)

    print 'Addresses needed: %d' % len(needed)
    for latlng in needed:
        street_address = google.latlng_to_address(latlng)
        db_address = database.Address(
            latlng=latlng, address=street_address, date=now)
        dbc.session.add(db_address)
        dbc.session.commit()


def _update_directions(dbc, portals):
    _update_paths(dbc, portals)
    _update_path_legs(dbc, portals)


def _update_paths(dbc, portals):
    now = time.time()
    combo_groups = _grouper(_portal_combos(portals), 64)
    for combo_group in combo_groups:
        filtered_combo_group = [x for x in combo_group if x is not None]
        needed = set()
        queries = collections.defaultdict(set)
        for begin_portal, end_portal, mode in filtered_combo_group:
            needed.add((begin_portal['latlng'], end_portal['latlng'], mode))
            queries[mode].add(begin_portal['latlng'])
        for mode, begin_portals in queries.iteritems():
            for row in dbc.session.query(database.Path).filter(
                    database.Path.mode == mode,
                    database.Path.begin_latlng.in_(begin_portals)):
                found = (row.begin_latlng, row.end_latlng, mode)
                needed.discard(found)

        for begin_latlng, end_latlng, mode in needed:
            dbc.session.add(
                database.Path(
                    begin_latlng=begin_latlng,
                    end_latlng=end_latlng,
                    mode=mode,
                    date=now))
    dbc.session.commit()


def _update_path_legs(dbc, portals):
    path_ids = set()
    for begin_portal, end_portal, mode in _portal_combos(portals):
        rows = dbc.session.query(database.Path).filter(
            database.Path.begin_latlng == begin_portal['latlng'],
            database.Path.end_latlng == end_portal['latlng'],
            database.Path.mode == mode)
        for row in rows:
            path_ids.add(row.id)
    _ensure_path_legs(dbc, path_ids)


def _ensure_path_legs(dbc, path_ids):
    path_ids = list(path_ids)
    random.shuffle(path_ids)
    print 'checking %d paths' % len(path_ids)
    for path_id in path_ids:
        _ensure_path_legs_by_path_id(dbc, path_id)


def _ensure_path_legs_by_path_id(dbc, path_id):
    now = time.time()
    path_complete = False
    db_path = dbc.session.query(database.Path).filter(
        database.Path.id == path_id).one()
    legs_of_interest = [(db_path.begin_latlng, db_path.end_latlng)]
    while not path_complete:
        rows = dbc.session.query(database.PathLeg).filter(
            database.PathLeg.path_id == path_id)
        path_legs = [row.id for row in rows]
        # do something here with known paths_legs and desired legs and
        # tsort

        for index, leg_of_interest in enumerate(legs_of_interest):
            _ensure_leg(dbc, path_id, leg_of_interest, db_path.mode)
            return


def _ensure_leg(dbc, path_id, leg_of_interest, mode):
    # First look to see if there is already a matching leg, and if so,
    # use it.  If not, try to find a new leg matching and save it.
    print '_ensure_leg', path_id, leg_of_interest, mode
    db_leg = dbc.session.query(database.Leg).filter(
        database.Leg.begin_latlng == leg_of_interest[0],
        database.Leg.end_latlng == leg_of_interest[1],
        database.Leg.mode == mode).one_or_none()
    if db_leg is None:
        google_leg = google.directions(leg_of_interest[0], leg_of_interest[1],
                                       mode)
        db_leg = database.Leg(begin_latlng=google_leg.begin_latlng,
                              end_latlng=google_leg.end_latlng,
                              mode=google_leg.mode,
                              date=time.time(),
                              duration=google_leg.duration,
                              polyline=google_leg.polyline)
        dbc.session.add(db_leg)
        dbc.session.flush()
    db_leg_path = database.PathLeg(leg_id=db_leg.id, path_id=path_id)
    dbc.session.add(db_leg_path)
    dbc.session.commit()


def _clean(dbc):
    now = time.time()
    oldest_allowed = now - MAX_AGE
    rows = dbc.session.query(database.Address).filter(
        database.Address.date < oldest_allowed)
    for row in rows:
        print 'Deleting ', row.date, row.address
        dbc.session.delete(row)
    rows = dbc.session.query(database.Leg).filter(
        database.Leg.date < oldest_allowed)
    for row in rows:
        print 'Delete ', row
    rows = dbc.session.query(database.Path).filter(
        database.Path.date < oldest_allowed)
    for row in rows:
        print 'Delete ', row
    dbc.session.commit()
