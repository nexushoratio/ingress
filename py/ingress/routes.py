"""Create and save routes between portals."""

import collections
import os

import humanize
import kmldom
import toposort

from ingress import bookmarks
from ingress import database
from ingress import google
from ingress import tsp

COLORS = {
    'walking': '#ff6eb4',
    'driving': '#00ff00',
}


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

    _save_as_kml(basename, path_info, optimized_info[0])
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
            ('legs', [legs_dict[latlng] for latlng in sorted_legs[:-1]],
             db_path, db_end))

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
    lat, lng = latlng.split(',')
    return float(lat), float(lng)


def _build_kml_portal(factory, portal):
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
    name = '%s for %s to %s' % (mode, humanize.h_m_s(duration), label)
    styleurl = '#%s' % mode
    placemark.set_name(name.encode('utf8'))
    placemark.set_styleurl(styleurl.encode('utf8'))


def _build_kml_legs(factory, legs):
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
                _finalize_kml_leg_placemark(placemark, current_mode, duration,
                                            label)
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
        _finalize_kml_leg_placemark(placemark, current_mode, duration,
                                    db_portal.label)
        yield placemark


def _save_as_kml(basename, path, duration):
    # https://developers.google.com/kml/documentation/kmlreference

    factory = kmldom.KmlFactory_GetFactory()
    kml = factory.CreateKml()
    doc = factory.CreateDocument()
    folder = factory.CreateFolder()

    folder.set_name('%s - %s' % (basename, humanize.h_m_s(duration)))
    doc.set_name(basename)
    doc.add_feature(folder)
    kml.set_feature(doc)

    for style_name in ('driving', 'walking'):
        style = factory.CreateStyle()
        line_style = factory.CreateLineStyle()
        color = line_style.get_color()

        style.set_id(style_name)
        style.set_linestyle(line_style)
        doc.add_styleselector(style)
        color.set_color_abgr(_kml_color(style_name))
        line_style.set_color(color)
        line_style.set_width(4)

    for item in path:
        type_ = item[0]
        if type_ == 'portal':
            placemark = _build_kml_portal(factory, item)
            folder.add_feature(placemark)
        elif type_ == 'legs':
            for placemark in _build_kml_legs(factory, item):
                folder.add_feature(placemark)
        else:
            raise Exception('Unknown type: %s' % type_)

    with open('%s-rt.kml' % basename, 'w') as f_kml:
        print >> f_kml, kmldom.SerializePretty(kml)


def _save_as_bookmarks(basename, path):
    pass


def _save_as_text(basename, path):
    pass


def _save_as_drawtools(basename, path):
    pass
