"""Functions for all things geo related."""

import collections
import functools
import itertools
import logging
import random
import sys
import time

import attr
import pyproj
import shapely
import rtree
import toposort

from pygraph.algorithms import traversal as pytraversal
from pygraph.classes import graph as pygraph
from pygraph.classes import exceptions as pyexceptions

from ingress import database
from ingress import bookmarks
from ingress import drawtools
from ingress import google
from ingress import json
from ingress import zcta as zcta_lib

MAX_AGE = 90 * 24 * 60 * 60
FUDGE_FACTOR = 1.1
MINIMAL_CLUSTER_SIZE = 10
START_DISTANCE = 75
MAX_DISTANCE = START_DISTANCE * 4 + 1


def register_module_parsers(ctx):
    """Parser registration API."""
    bm_parser = ctx.shared_parsers['bm_parser']
    dt_parser = ctx.shared_parsers['dt_parser']
    file_parser = ctx.shared_parsers['file_parser']
    glob_parser = ctx.shared_parsers['glob_parser']

    parser = ctx.subparsers.add_parser(
        'update',
        parents=[bm_parser],
        description=update.__doc__,
        help=update.__doc__)
    parser.add_argument(
        '--noaddresses',
        action='store_false',
        dest='addresses',
        help='Disable updating addresses.')
    parser.add_argument(
        '--addresses', action='store_true', help='Enable updating addresses.')
    parser.add_argument(
        '--nodirections',
        action='store_false',
        dest='directions',
        help='Disable updating directions.')
    parser.add_argument(
        '--directions',
        action='store_true',
        help='Enable updating directions..')
    parser.set_defaults(func=update)

    parser = ctx.subparsers.add_parser(
        'bounds',
        parents=[dt_parser, glob_parser],
        description=bounds.__doc__,
        help=bounds.__doc__)
    parser.set_defaults(func=bounds)

    parser = ctx.subparsers.add_parser(
        'trim',
        parents=[bm_parser, dt_parser],
        description=trim.__doc__,
        help=trim.__doc__)
    parser.set_defaults(func=trim)

    parser = ctx.subparsers.add_parser(
        'cluster',
        parents=[file_parser],
        description=cluster.__doc__,
        help=cluster.__doc__)
    parser.set_defaults(func=cluster)

    parser = ctx.subparsers.add_parser(
        'make-donuts',
        parents=[dt_parser],
        description=donuts.__doc__,
        help=donuts.__doc__)
    parser.add_argument(
        '-s',
        '--size',
        action='store',
        type=int,
        required=True,
        help='Number of portals per bite.')
    parser.add_argument(
        '-b',
        '--bites',
        action='store',
        type=int,
        default=sys.maxint,
        help='Limit the number of bites.')
    parser.add_argument(
        '-p',
        '--pattern',
        action='store',
        default='bm-donut-{size}-{bite:0{width}d}.json',
        help=(
            'Pattern used to name the output files.  Uses PEP 3101 formatting'
            ' strings with the following fields:  size, width, bite'))
    parser.set_defaults(func=donuts)


def update(args, dbc):
    """Update the locations and directions for portals in a bookmarks file."""
    portals = bookmarks.load(args.bookmarks)
    _clean(dbc)
    if args.addresses:
        _update_addresses(dbc, portals)
    if args.directions:
        _update_directions(dbc, portals)


def bounds(args, dbc):
    """Create a drawtools file outlining portals in multiple bookmarks files."""
    collections = list()
    for filename in itertools.chain(*args.glob):
        data = bookmarks.load(filename)
        points = list()
        for bookmark in data.itervalues():
            latlng = _latlng_str_to_floats(bookmark['latlng'])
            lnglat = (latlng[1], latlng[0])
            point = shapely.geometry.Point(lnglat)
            points.append(point)
        multi_points = shapely.geometry.MultiPoint(points)
        collections.append(multi_points)
    drawtools.save_bounds(args.drawtools, collections)


def trim(args, dbc):
    """Trim a bookmarks file to only include portals inside a bounds."""
    if shapely.speedups.available:
        shapely.speedups.enable()

    portals = bookmarks.load(args.bookmarks)
    collection = drawtools.load_polygons(args.drawtools)

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


def donuts(args, dbc):
    """Automatically group portals into COUNT sized bookmarks files.

    The idea is to provide a series of bookmarks that would be suitably
    sized groups for efficient capturing.

    Given a starting marker specified in the drawtools file, a circle
    (donut hole) that includes COUNT portals will be created.  The size
    of this hole will inform the size of concentric rings (donuts).

    The donut will be broken down into bites that contain roughly COUNT
    portals.  The command will try to balance between between the number
    of portals in a bite and how big (in area) a bite would be.  For
    example, it will try to avoid having a bite be the entire donut
    because it reaches out to a sparsely populated area.
    """
    point = drawtools.load_point(args.drawtools)
    transform = functools.partial(
        pyproj.transform,
        pyproj.Proj(proj='latlong'),
        pyproj.Proj(
            proj='stere', lat_0=point.y, lon_0=point.x, lat_ts=point.y))
    ordered_sprinkles = _order_by_distance(point, dbc)
    full_donuts, delta = _donuts(ordered_sprinkles, args.size)
    transformed_points = _points_from_sprinkles(full_donuts[0], transform)
    max_area = transformed_points.convex_hull.area * FUDGE_FACTOR
    max_length = delta * FUDGE_FACTOR
    print 'max_line:', max_length
    print 'max_area:', max_area
    bites = _bites(full_donuts, args.size, transform, max_length, max_area)
    print 'There are %d donut bites.' % len(bites)
    width = len(str(len(bites)))
    for nibble, bite in enumerate(bites):
        if nibble < args.bites:
            filename = args.pattern.format(
                size=args.size, width=width, bite=nibble)
            guids = (sprinkle.guid for sprinkle in bite)
            bookmarks.save_from_guids(guids, filename, dbc)


def cluster(args, dbc):
    """Find clusters of portals together and save them in a file."""
    rtree_index = _rtree_index(_node_map(dbc))
    graph = pygraph.graph()
    graph.add_nodes(rtree_index.node_map.iterkeys())  # pylint: disable=no-member
    clusters = set()

    distance = START_DISTANCE
    while distance < MAX_DISTANCE:
        print 'Looking for distance %d' % distance
        to_clean = set()

        _add_edges(graph, rtree_index.index, rtree_index.node_map, distance)
        print 'Extracting clusters from graph...'
        for new_cluster in _extract_clusters(graph):
            clusters.add((distance, new_cluster))
            to_clean.update(new_cluster)
        print 'Clusters extracted.'

        _clean_clustered_points(graph, rtree_index.index, rtree_index.node_map,
                                to_clean)
        distance *= 2

    _finalize_and_save(args.filename, clusters, rtree_index)


def _finalize_and_save(filename, clusters, rtree_index):
    logging.info('_finalize_and_save: %d clusters into %s',
                 len(clusters), filename)
    zcta = zcta_lib.Zcta()
    node_map_by_projected_coords = dict(
        (node.projected_point.coords[0], node)
        for node in rtree_index.node_map.itervalues())
    clustered = list()
    for distance, nodes in clusters:
        projected_points = [
            rtree_index.node_map[idx].projected_point for idx in nodes
        ]
        latlng_points = (rtree_index.node_map[idx].latlng_point
                         for idx in nodes)
        multi_point = shapely.geometry.MultiPoint(projected_points)
        latlng_centroid = shapely.ops.transform(rtree_index.reverse_transform,
                                                multi_point.centroid)
        projected_hull = multi_point.convex_hull
        latlng_hull = (node_map_by_projected_coords[coord]
                       for coord in multi_point.convex_hull.exterior.coords)
        cluster = {
            'area': projected_hull.area,
            'centroid': {
                'lat': latlng_centroid.y,
                'lng': latlng_centroid.x,
            },
            'code': zcta.code_from_point(latlng_centroid),
            'density': len(nodes) / projected_hull.area,
            'distance': distance,
            'hull': [{
                'lat': node.latlng_point.y,
                'lng': node.latlng_point.x,
            } for node in latlng_hull],
            'points': [{
                'lat': point.y,
                'lng': point.x,
            } for point in latlng_points],
        }
        clustered.append(cluster)

    json.save(filename, clustered)
    logging.info('_finalize_and_save: done')


def _clean_clustered_points(graph, index, node_map, new_cluster):
    logging.info('_clean_clustered_points: %d nodes', len(new_cluster))
    print 'Cleaning out clustered points...'
    for node_index in new_cluster:
        node = node_map[node_index]
        index.delete(node_index, node.projected_coords)
        graph.del_node(node_index)
    logging.info('_clean_clustered_points: points left in graph: %d',
                 len(graph.nodes()))


def _extract_clusters(graph):
    logging.info('entered _extract_clusters')
    visited = set()
    for node in graph.nodes():
        if node in visited:
            continue
        visited.add(node)
        other_nodes = frozenset(pytraversal.traversal(graph, node, 'pre'))
        visited.update(other_nodes)
        if len(other_nodes) >= MINIMAL_CLUSTER_SIZE:
            yield other_nodes
    logging.info('leaving _extract_clusters')


def _add_edges(graph, index, node_map_by_index, max_distance):
    logging.info('_add_edges for %d', max_distance)
    node_count = 0
    edge_count = 0
    result_limit = 1
    for node_index in graph.nodes():
        node_count += 1
        if node_count % 10000 == 0:
            print 'at node count', node_count
        node = node_map_by_index[node_index]
        done = False
        while not done:
            other_nodes = list(
                index.nearest(
                    node.projected_coords, num_results=result_limit))
            furthest = node_map_by_index[other_nodes[-1]]
            distance = node.projected_point.distance(furthest.projected_point)
            done = distance > max_distance
            if not done:
                result_limit *= 2

        for other_node_index in other_nodes:
            if node_index != other_node_index:
                other_node = node_map_by_index[other_node_index]
                distance = node.projected_point.distance(
                    other_node.projected_point)
                if distance < max_distance:
                    edge = (node_index, other_node_index)
                    try:
                        graph.add_edge(edge)
                        edge_count += 1
                    except pyexceptions.AdditionError:
                        pass
    logging.info('_add_edges: edges added: %d', edge_count)


@attr.s  # pylint: disable=missing-docstring,too-few-public-methods
class NodeData(object):
    latlng_point = attr.ib(init=False, default=None)
    latlng_point_wkt = attr.ib(init=False, default=None)
    projected_point = attr.ib(init=False, default=None)
    projected_point_wkt = attr.ib(init=False, default=None)
    projected_coords = attr.ib(init=False, default=None)
    # We use a set for guids because we may have two portals at the same
    # latlng.
    guids = attr.ib(init=False, default=attr.Factory(set))


def _closest_point(target, points):
    # Find a known point that is the closed to the target point
    logging.info('_closest_point: near %s', target)

    @attr.s  # pylint: disable=missing-docstring,too-few-public-methods
    class DistancePoint(object):
        distance = attr.ib()
        point = attr.ib()

    geod = pyproj.Geod(ellps='WGS84')
    tlat = target.y
    tlng = target.x
    distances = (DistancePoint(
        distance=geod.inv(point.x, point.y, tlng, tlat)[2], point=point)
                 for point in points)
    result = min(distances, key=lambda x: x.distance)
    logging.info('_closest_point: found %s', result)
    return result.point


@attr.s  # pylint: disable=missing-docstring,too-few-public-methods
class RtreeIndex(object):
    index = attr.ib()
    forward_transform = attr.ib()
    reverse_transform = attr.ib()
    node_map = attr.ib()


def _rtree_index(node_map_by_wkt):
    # First, find a good centroid to use for a projection, then use that
    # projection for the index
    logging.info('_rtree_index: nodes: %d', len(node_map_by_wkt))
    nodes = list(node.latlng_point for node in node_map_by_wkt.itervalues())
    old_centroid = None
    new_centroid = nodes[0]
    latlng_projection = pyproj.Proj(proj='latlong')

    while new_centroid != old_centroid:
        logging.info('new_centroid: %s', new_centroid)
        old_centroid = new_centroid
        stere_projection = pyproj.Proj(
            proj='stere',
            lat_0=new_centroid.y,
            lon_0=new_centroid.x,
            lat_ts=new_centroid.y)
        forward_transform = functools.partial(
            pyproj.transform, latlng_projection, stere_projection)
        reverse_transform = functools.partial(
            pyproj.transform, stere_projection, latlng_projection)
        latlng_multi_points = shapely.geometry.MultiPoint(nodes)
        stere_multi_points = shapely.ops.transform(forward_transform,
                                                   latlng_multi_points)
        centroid = shapely.ops.transform(reverse_transform,
                                         stere_multi_points.centroid)
        new_centroid = _closest_point(centroid, latlng_multi_points)

    logging.info('projecting around %s', new_centroid)
    node_map_by_index = _node_map_by_index(
        enumerate(itertools.izip(stere_multi_points, latlng_multi_points)),
        node_map_by_wkt)

    logging.info('building rtree index')
    index = rtree.index.Index((idx, node.projected_coords, None)
                              for idx, node in node_map_by_index.iteritems())
    logging.info('built rtree index')
    return RtreeIndex(
        index=index,
        forward_transform=forward_transform,
        reverse_transform=reverse_transform,
        node_map=node_map_by_index)


def _node_map_by_index(index_pair, node_map_by_wkt):
    logging.info('entered _node_map_by_index')
    node_map_by_index = dict()
    for index, pair in index_pair:
        stere, latlng = pair
        node = node_map_by_wkt[latlng.wkt]
        node.projected_point = stere
        node.projected_point_wkt = stere.wkt
        node.projected_coords = (stere.x, stere.y, stere.x, stere.y)
        node_map_by_index[index] = node
    logging.info('leaving _node_map_by_index')
    return node_map_by_index


def _node_map(dbc):
    """Create a mapping from latlngs to portal guids."""
    logging.info('entered _node_map_by_index')
    node_map = collections.defaultdict(NodeData)
    for db_portal in dbc.session.query(database.Portal):
        point = _latlng_str_to_point(db_portal.latlng)
        node = node_map[point.wkt]
        node.latlng_point = point
        node.latlng_point_wkt = point.wkt
        node.guids.add(db_portal.guid)
    logging.info('_node_map: nodes mapped: %d', len(node_map))
    return node_map


def _points_from_sprinkles(donut, transform):
    points = (_latlng_str_to_floats(sprinkle.latlng) for sprinkle in donut)
    multi_points = shapely.geometry.MultiPoint(
        [(lng, lat) for lat, lng in points])
    transformed_points = shapely.ops.transform(transform, multi_points)
    return transformed_points


def _bites(full_donuts, count, transform, max_length, max_area):
    all_bites = list()
    _order_sprinkles(full_donuts)
    for donut in full_donuts:
        bite_count = len(donut) / count + bool(len(donut) % count)
        overlap = 1.0 * ((bite_count * count) - len(donut)) / bite_count
        donut *= 2
        for nibble in xrange(bite_count):
            start = int(round(count - overlap) * nibble)
            stop = start + count
            bite = donut[start:stop]
            for smaller_bite in _smaller_bites(bite, transform, max_length,
                                               max_area):
                all_bites.append(smaller_bite)
    return all_bites


def _smaller_bites(bite, transform, max_length, max_area):
    """Examine a bite for various issues, maybe resulting in smaller bites."""
    transformed_points = _points_from_sprinkles(bite, transform)
    good = True
    if transformed_points.convex_hull.area > max_area:
        print 'too big:', transformed_points.convex_hull.area, max_area
        good = False
    if len(transformed_points) > 1:
        length = transformed_points.minimum_rotated_rectangle.length / len(
            transformed_points)
        if length > max_length:
            print 'too long:', length, max_length
            good = False

    if len(transformed_points) == 1:
        good = True

    if good:
        yield bite
    else:
        smaller_bites = _smaller_bites(bite[:-1], transform, max_length,
                                       max_area)
        yield smaller_bites.next()
        rest = list()
        for sprinkles in smaller_bites:
            rest.extend(sprinkles)
        rest.append(bite[-1])
        for smaller_bite in _smaller_bites(rest, transform, max_length,
                                           max_area):
            yield smaller_bite


def _order_sprinkles(full_donuts):
    # sort the sprinkles by angle
    for donut in full_donuts:
        start = donut[0].angle
        for sprinkle in donut:
            if sprinkle.angle < start:
                sprinkle.angle += 360
        donut.sort(key=lambda sprinkle: sprinkle.angle)


def _donuts(all_sprinkles, count):
    """Each donuts should have at least count sprinkles on it."""
    donuts = list()
    delta = all_sprinkles[count].distance
    radius = 0
    while all_sprinkles:
        donut = list()
        # Keep making donuts bigger until it has at least count sprinkles on
        # it.
        while len(donut) < count:
            radius += delta
            donut_sprinkles = [
                sprinkle for sprinkle in all_sprinkles
                if sprinkle.distance < radius
            ]
            donut.extend(donut_sprinkles)
            del all_sprinkles[:len(donut_sprinkles)]
            # toss the left over sprinkles onto the last donut
            if len(all_sprinkles) < count:
                donut.extend(all_sprinkles)
                del all_sprinkles[:]
        donuts.append(donut)
    return donuts, delta


@attr.s  # pylint: disable=missing-docstring,too-few-public-methods
class PortalGeo(object):
    distance = attr.ib()
    angle = attr.ib()
    guid = attr.ib()
    latlng = attr.ib()


def _order_by_distance(point, dbc):
    geod = pyproj.Geod(ellps='WGS84')
    lat = point.y
    lng = point.x

    rows = dbc.session.query(database.Portal)
    portals = list()
    for db_portal in rows:
        plat, plng = _latlng_str_to_floats(db_portal.latlng)
        angle, rangle, distance = geod.inv(lng, lat, plng, plat)
        portal = PortalGeo(
            distance=distance,
            angle=angle,
            guid=db_portal.guid,
            latlng=db_portal.latlng)
        portals.append(portal)

    portals.sort(key=lambda x: x.distance)
    return portals


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


def _latlng_str_to_point(latlng_as_str):
    lat, lng = _latlng_str_to_floats(latlng_as_str)
    return shapely.geometry.Point(lng, lat)


def _distance(begin, end):
    geod = pyproj.Geod(ellps='WGS84')
    blat, blng = _latlng_str_to_floats(begin)
    elat, elng = _latlng_str_to_floats(end)
    fwd, rev, dist = geod.inv(blng, blat, elng, elat)
    del fwd, rev
    return dist
