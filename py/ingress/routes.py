"""Create and save routes between portals."""

import collections
import os
import toposort

from ingress import bookmarks
from ingress import database
from ingress import tsp


def route(args, dbc):
    """Calculate an optimal route between portals."""
    mode_cost_map = dict()
    portals = bookmarks.load(args.bookmarks)
    portal_keys = portals.keys()
    portal_keys.append(portal_keys[0])
    optimized_info = tsp.optimize(
        portal_keys,
        lambda start, end: _cost(dbc, mode_cost_map, args.walk_auto, start, end)
    )

    basename = os.path.splitext(args.bookmarks)[0]

    path_info = _path_info(dbc, optimized_info[1], mode_cost_map)
    print path_info
    _save_as_kml(basename, path_info)
    _save_as_bookmarks(basename, path_info)
    _save_as_text(basename, path_info)
    _save_as_drawtools(basename, path_info)


def _cost(dbc, mode_cost_map, max_walking_time_allowed, begin, end):
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
    cost = 0
    for path_leg in dbc.session.query(database.PathLeg).filter(
            database.PathLeg.path_id == path.id):
        leg = dbc.session.query(database.Leg).get(path_leg.leg_id)
        cost += leg.duration

    return cost


def _path_info(dbc, opt_path, mode_cost_map):
    items = list()
    for begin, end in zip(opt_path, opt_path[1:]):
        mode, cost = mode_cost_map[(begin, end)]
        db_begin = dbc.session.query(database.Portal).get(begin)
        db_end = dbc.session.query(database.Portal).get(end)
        items.append(('portal', db_begin))
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
            ('legs', [legs_dict[latlng] for latlng in sorted_legs[:-1]]))

    return items


def _save_as_kml(basename, path):
    pass


def _save_as_bookmarks(basename, path):
    pass


def _save_as_text(basename, path):
    pass


def _save_as_drawtools(basename, path):
    pass
