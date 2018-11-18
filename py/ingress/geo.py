"""Functions for all things geo related."""

import collections
import itertools
import random
import time

import pyproj
import shapely.speedups
import toposort

from ingress import database
from ingress import bookmarks
from ingress import google
from ingress import json

MAX_AGE = 90 * 24 * 60 * 60


def register_shared_parsers(ctx):
    """Parser registration API."""
    dt_parser = ctx.argparse.ArgumentParser(add_help=False)
    dt_parser.add_argument(
        '-d',
        '--drawtools',
        action='store',
        required=True,
        help='IITC drawtools json file to use')

    ctx.shared_parsers['dt_parser'] = dt_parser


def register_module_parsers(ctx):
    """Parser registration API."""
    bm_parser = ctx.shared_parsers['bm_parser']
    dt_parser = ctx.shared_parsers['dt_parser']

    parser_update = ctx.subparsers.add_parser(
        'update',
        parents=[bm_parser],
        description=update.__doc__,
        help=update.__doc__)
    parser_update.add_argument(
        '--noaddresses',
        action='store_false',
        dest='addresses',
        help='Disable updating addresses.')
    parser_update.add_argument(
        '--addresses', action='store_true', help='Enable updating addresses.')
    parser_update.add_argument(
        '--nodirections',
        action='store_false',
        dest='directions',
        help='Disable updating directions.')
    parser_update.add_argument(
        '--directions',
        action='store_true',
        help='Enable updating directions..')
    parser_update.set_defaults(func=update)

    parser_bounds = ctx.subparsers.add_parser(
        'bounds',
        parents=[bm_parser, dt_parser],
        description=bounds.__doc__,
        help=bounds.__doc__)
    parser_bounds.set_defaults(func=bounds)

    parser_trim = ctx.subparsers.add_parser(
        'trim',
        parents=[bm_parser, dt_parser],
        description=trim.__doc__,
        help=trim.__doc__)
    parser_trim.set_defaults(func=trim)


def update(args, dbc):
    """Update the locations and directions for portals in a bookmarks file."""
    portals = bookmarks.load(args.bookmarks)
    _clean(dbc)
    if args.addresses:
        _update_addresses(dbc, portals)
    if args.directions:
        _update_directions(dbc, portals)


def bounds(args, dbc):
    """Create a drawtools file outlining portals in a bookmarks file."""
    if shapely.speedups.available:
        shapely.speedups.enable()

    data = bookmarks.load(args.bookmarks)
    points = list()
    for bookmark in data.itervalues():
        latlng = _latlng_str_to_floats(bookmark['latlng'])
        lnglat = (latlng[1], latlng[0])
        point = shapely.geometry.Point(lnglat)
        points.append(point)

    collection = shapely.geometry.MultiPoint(points)
    hull_shapely = collection.convex_hull.exterior.coords

    hull = [{'lng': point[0], 'lat': point[1]} for point in hull_shapely]
    json.save(args.drawtools, [{'type': 'polygon', 'latLngs': hull}])


def trim(args, dbc):
    """Trim a bookmarks file to only include portals inside a bounds."""
    if shapely.speedups.available:
        shapely.speedups.enable()

    portals = bookmarks.load(args.bookmarks)
    outlines = json.load(args.drawtools)
    polygons = _outlines_to_polygons(outlines)

    collection = shapely.geometry.MultiPolygon(polygons)
    to_delete = set()
    for guid, portal in portals.iteritems():
        latlng = _latlng_str_to_floats(portal['latlng'])
        lnglat = (latlng[1], latlng[0])
        point = shapely.geometry.Point(lnglat)
        if not point.intersects(collection):
            to_delete.add(guid)
    for guid in to_delete:
        del portals[guid]

    if to_delete:
        print 'deleting:', to_delete
        bookmarks.save(portals, args.bookmarks)


def _outlines_to_polygons(outlines):
    polygons = list()
    for outline in outlines:
        typ = outline['type']
        if typ == 'polygon':
            points = [(point['lng'], point['lat'])
                      for point in outline['latLngs']]
            polygons.append(shapely.geometry.Polygon(points))
        elif typ == 'circle':
            # Turn it into a finely defined polygon
            geod = pyproj.Geod(ellps='WGS84')
            dist = outline['radius']
            lat = outline['latLng']['lat']
            lng = outline['latLng']['lng']
            points = [
                geod.fwd(lng, lat, angle, dist)[:2]
                for angle in range(0, 360, 5)
            ]
        else:
            raise Exception('%s is a type not yet handled.' % typ)

    return polygons


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
    print 'Paths to check: %d' % len(path_ids)
    for count, path_id in enumerate(path_ids):
        _ensure_path_legs_by_path_id(dbc, count, path_id)


def _ensure_path_legs_by_path_id(dbc, count, path_id):
    db_path = dbc.session.query(database.Path).get(path_id)

    print '%4d path_id: %4d|%23s|%23s' % (count, path_id, db_path.begin_latlng,
                                          db_path.end_latlng)

    now = time.time()
    path_complete = False
    attempts = 1
    while not path_complete and attempts < 5:
        legs_of_interest = set()
        legs = collections.defaultdict(set)
        for leg in dbc.session.query(database.Leg).join(
                database.PathLeg).filter(database.PathLeg.path_id == path_id):
            legs[leg.begin_latlng].add(leg.end_latlng)
        if legs:
            sorted_legs = list(toposort.toposort(legs))
            if len(sorted_legs[0]) > 1:
                print 'There is a hole for path %d.  Clearing.' % path_id
                dbc.session.query(database.PathLeg).filter(
                    database.PathLeg.path_id == path_id).delete()
                dbc.session.commit()
            else:
                first = sorted_legs[-1].pop()
                last = sorted_legs[0].pop()
                if first != db_path.begin_latlng:
                    legs_of_interest.add((db_path.begin_latlng, first))
                if last != db_path.end_latlng:
                    legs_of_interest.add((last, db_path.end_latlng))
                path_complete = not legs_of_interest
        else:
            legs_of_interest.add((db_path.begin_latlng, db_path.end_latlng))

        while legs_of_interest and attempts < 15:
            attempts += 1
            leg = legs_of_interest.pop()
            more_legs = _ensure_leg(dbc, path_id, leg, db_path.mode)
            legs_of_interest.update(more_legs)


def _ensure_leg(dbc, path_id, leg_of_interest, mode):
    # First look to see if there is already a matching leg, and if so,
    # use it.  If not, try to find a new leg matching and save it.
    begin, end = leg_of_interest
    db_leg = dbc.session.query(database.Leg).filter(
        database.Leg.begin_latlng == begin, database.Leg.end_latlng == end,
        database.Leg.mode == mode).one_or_none()
    if db_leg is None:
        google_leg = _get_reasonable_google_leg(begin, end, mode)

        # Now check to see if THIS exists:
        db_leg = dbc.session.query(database.Leg).filter(
            database.Leg.begin_latlng == google_leg.begin_latlng,
            database.Leg.end_latlng == google_leg.end_latlng,
            database.Leg.mode == google_leg.mode).one_or_none()
        if db_leg is None:
            # finally add it
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

    # Just because we asked for something, it doesn't mean we got it
    new_legs = set()
    if begin != db_leg.begin_latlng:
        new_legs.add((begin, db_leg.begin_latlng))
    if db_leg.end_latlng != end:
        new_legs.add((db_leg.end_latlng, end))
    return new_legs


def _get_reasonable_google_leg(begin, end, mode):
    google_leg = google.directions(begin, end, mode)
    crow_flies = _distance(begin, end)
    if mode == 'driving' and (crow_flies < 120 or google_leg.duration < 30):
        google_leg = google.directions(begin, end, 'walking')

    if _distance(google_leg.begin_latlng, google_leg.end_latlng) < 10:
        google_leg.begin_latlng = begin
        google_leg.end_latlng = end
        google_leg.mode = 'walking'
        google_leg.duration = crow_flies  # seems like a good guess
        google_leg.polyline = unicode(
            google.encode_polyline((_latlng_str_to_floats(begin),
                                    _latlng_str_to_floats(end))))

    print 'wanted: %23s %23s %7s %5d' % (begin, end, mode, crow_flies)
    print 'got:    %23s %23s %7s %5d' % (
        google_leg.begin_latlng, google_leg.end_latlng, google_leg.mode,
        _distance(google_leg.begin_latlng, google_leg.end_latlng))
    return google_leg


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


def _latlng_str_to_floats(latlng_as_str):
    lat, lng = latlng_as_str.split(',')
    return float(lat), float(lng)


def _distance(begin, end):
    geod = pyproj.Geod(ellps='WGS84')
    blat, blng = _latlng_str_to_floats(begin)
    elat, elng = _latlng_str_to_floats(end)
    fwd, rev, dist = geod.inv(blng, blat, elng, elat)
    del fwd, rev
    return dist
