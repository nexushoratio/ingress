"""Create and save routes between portals."""

import os

from ingress import bookmarks
from ingress import database
from ingress import tsp


def route(args, dbc):
    """Calculate an optimal route between portals."""
    mode_cost = dict()
    portals = bookmarks.load(args.bookmarks)
    portal_keys = portals.keys()
    portal_keys.append(portal_keys[0])
    optimized_path = tsp.optimize(
        portal_keys,
        lambda start, end: _cost(dbc, mode_cost, args.walk_auto, start, end))

    basename = os.path.splitext(args.bookmarks)[0]

    _save_as_kml(basename, optimized_path)
    _save_as_bookmarks(basename, optimized_path)
    _save_as_text(basename, optimized_path)
    _save_as_drawtools(basename, optimized_path)


def _cost(dbc, mode_cost, max_walking_time_allowed, begin, end):
    cost = mode_cost.get((begin, end))
    if cost:
        return cost
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
    else:
        cost = driving
    mode_cost[(begin, end)] = cost
    return cost


def _path_cost(dbc, path):
    cost = 0
    for path_leg in dbc.session.query(database.PathLeg).filter(
            database.PathLeg.path_id == path.id):
        leg = dbc.session.query(database.Leg).get(path_leg.leg_id)
        cost += leg.duration

    return cost


def _save_as_kml(basename, path):
    pass


def _save_as_bookmarks(basename, path):
    pass


def _save_as_text(basename, path):
    pass


def _save_as_drawtools(basename, path):
    pass
