"""Create and save routes between portals."""

from __future__ import annotations

import collections
import os
import typing

import humanize
# import kmldom
import toposort

from ingress import bookmarks
from ingress import database
from ingress import google
from ingress import tsp

if typing.TYPE_CHECKING:  # pragma: no cover
    import argparse

    from mundane import app

COLORS = {
    'walking': '#ff6eb4',
    'driving': '#00ff00',
}


def mundane_commands(ctx: app.ArgparseApp):
    """Register commands."""
    bm_flags = ctx.get_shared_parser('bookmarks')

    parser = ctx.register_command(route, parents=[bm_flags])
    parser.add_argument(
        '-w',
        '--walk-auto',
        action='store',
        type=int,
        help='Longest walk time to automatically accept.',
        default=300)


def route(args: argparse.Namespace) -> int:
    """Calculate an optimal route between portals listed in a bookmarks file."""
    dbc = args.dbc
    mode_cost_map: dict[tuple[str, str], tuple[str, float]] = dict()
    portals = bookmarks.load(args.bookmarks)
    portal_keys = list(portals.keys())
    portal_keys.append(portal_keys[0])
    optimized_info = tsp.optimize(
        portal_keys, lambda start, end: _cost(
            dbc, mode_cost_map, args.walk_auto, start, end))

    basename = os.path.splitext(args.bookmarks)[0]

    path_info = _path_info(dbc, optimized_info[1], mode_cost_map)

    _save_as_kml(basename, path_info, optimized_info[0])
    _save_as_bookmarks(basename, path_info)
    _save_as_text(basename, path_info)
    _save_as_drawtools(basename, path_info)

    return 0


def _cost(dbc, mode_cost_map, max_walking_time_allowed, begin, end):  # pylint: disable=too-many-locals
    """Placeholder docstring for private function."""
    mode_cost = mode_cost_map.get((begin, end))
    if mode_cost:
        return mode_cost[1]
    costs = dict()
    begin_portal = dbc.session.query(database.Portal).get(begin)
    end_portal = dbc.session.query(database.Portal).get(end)
    paths = dbc.session.query(database.Path).filter(
        database.Path.begin_latlng == begin_portal.latlng,
        database.Path.end_latlng == end_portal.latlng)
    for path in paths:
        costs[path.mode] = _path_cost(dbc, path)

    walking = costs['walking']
    driving = costs['driving']
    walking_to_driving = 1.0 * walking / driving
    if walking < max_walking_time_allowed or walking_to_driving < 1.1:
        cost = walking
        mode = 'walking'
    else:
        cost = driving
        mode = 'driving'
    mode_cost_map[(begin, end)] = (mode, cost)
    return cost


def _path_cost(dbc, path):
    """Placeholder docstring for private function."""
    cost = 0
    for path_leg in dbc.session.query(
            database.PathLeg).filter(database.PathLeg.path_id == path.id):
        leg = dbc.session.query(database.Leg).get(path_leg.leg_id)
        cost += leg.duration

    return cost


def _path_info(dbc, opt_path, mode_cost_map):
    """Placeholder docstring for private function."""
    items = list()
    for begin, end in zip(opt_path, opt_path[1:]):
        mode, _ = mode_cost_map[(begin, end)]
        db_begin = dbc.session.query(database.Portal).get(begin)
        db_end = dbc.session.query(database.Portal).get(end)
        db_address = dbc.session.query(database.Address).filter(
            database.Address.latlng == db_begin.latlng).one()
        items.append(('portal', db_begin, db_address))
        db_path = dbc.session.query(database.Path).filter(
            database.Path.mode == mode,
            database.Path.begin_latlng == db_begin.latlng,
            database.Path.end_latlng == db_end.latlng).one()
        legs_set = collections.defaultdict(set)
        legs_dict = dict()
        for db_leg in dbc.session.query(database.Leg).join(
                database.PathLeg).filter(
                    database.PathLeg.path_id == db_path.id):
            legs_set[db_leg.begin_latlng].add(db_leg.end_latlng)
            legs_dict[db_leg.begin_latlng] = db_leg
        sorted_legs = list(reversed(toposort.toposort_flatten(legs_set)))
        items.append(
            (
                'legs', [legs_dict[latlng]
                         for latlng in sorted_legs[:-1]], db_path, db_end))

    return items


def _kml_color(mode):
    """RGB -> ABGR"""
    color = COLORS[mode]
    colors = {
        'red': color[1:3],
        'green': color[3:5],
        'blue': color[5:7],
    }
    kml_color = 'ff%(blue)2s%(green)2s%(red)2s' % colors
    return kml_color


def _latlng_as_doubles(latlng):
    """Placeholder docstring for private function."""
    lat, lng = latlng.split(',')
    return float(lat), float(lng)


def _build_kml_portal(factory, portal):
    """Placeholder docstring for private function."""
    placemark = factory.CreatePlacemark()
    coordinates = factory.CreateCoordinates()
    point = factory.CreatePoint()
    db_portal = portal[1]
    db_address = portal[2]
    placemark.set_name(db_portal.label.encode('utf8'))
    placemark.set_description(db_address.address.encode('utf8'))
    lat, lng = _latlng_as_doubles(db_portal.latlng)
    coordinates.add_latlng(lat, lng)
    point.set_coordinates(coordinates)
    placemark.set_geometry(point)

    return placemark


def _finalize_kml_leg_placemark(placemark, mode, duration, label):
    """Placeholder docstring for private function."""
    name = f'{mode} for {humanize.precisedelta(duration)} to {label}'
    styleurl = f'#{mode}'
    placemark.set_name(name.encode('utf8'))
    placemark.set_styleurl(styleurl.encode('utf8'))


def _build_kml_legs(factory, legs):
    """Placeholder docstring for private function."""
    db_path = legs[2]
    db_portal = legs[3]

    current_mode = None
    placemark = None
    duration = 0

    for db_leg in legs[1]:
        if db_leg.mode != current_mode:
            if placemark:
                if db_path.mode == current_mode:
                    label = db_portal.label
                else:
                    label = 'waypoint'
                _finalize_kml_leg_placemark(
                    placemark, current_mode, duration, label)
                yield placemark
            current_mode = db_leg.mode
            placemark = factory.CreatePlacemark()
            coordinates = factory.CreateCoordinates()
            line_string = factory.CreateLineString()
            duration = 0
            line_string.set_coordinates(coordinates)
            placemark.set_geometry(line_string)
        duration += db_leg.duration
        for lat, lng in google.decode_polyline(db_leg.polyline):
            coordinates.add_latlng(lat, lng)

    if placemark:
        _finalize_kml_leg_placemark(
            placemark, current_mode, duration, db_portal.label)
        yield placemark


def _save_as_kml(basename, path, duration):
    """Placeholder docstring for private function."""
    # https://developers.google.com/kml/documentation/kmlreference
    del basename
    del path
    del duration


def _save_as_bookmarks(basename, path):
    """Placeholder docstring for private function."""
    del basename
    del path


def _save_as_text(basename, path):
    """Placeholder docstring for private function."""
    del basename
    del path


def _save_as_drawtools(basename, path):
    """Placeholder docstring for private function."""
    del basename
    del path
