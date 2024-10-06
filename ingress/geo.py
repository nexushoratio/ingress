"""Functions for all things geo related."""

from __future__ import annotations

import collections
import dataclasses
import itertools
import logging
import math
import operator
import random
import sys
import time
import typing

import pyproj
import shapely  # type: ignore[import]
import toposort

# from pygraph.algorithms import traversal as pytraversal
# from pygraph.classes import graph as pygraph
# from pygraph.classes import exceptions as pyexceptions

from ingress import database
from ingress import bookmarks
from ingress import drawtools
from ingress import google
from ingress import json
from ingress import rtree

if typing.TYPE_CHECKING:  # pragma: no cover
    import argparse

    from mundane import app

MAX_AGE = 90 * 24 * 60 * 60
FUDGE_FACTOR = 1.1
MINIMAL_CLUSTER_SIZE = 10
START_DISTANCE = 75
MAX_DISTANCE = START_DISTANCE * 4 + 1


@dataclasses.dataclass(kw_only=True)
class Sprinkle:
    """Pre-computed information about portals useful for making donuts."""
    distance: float
    azimuth: float
    guid: str


DistanceCache: typing.TypeAlias = dict[
    tuple[database.geoalchemy2.elements.WKBElement,
          database.geoalchemy2.elements.WKBElement], float]

# A Donut is a really big Bite
Bite: typing.TypeAlias = list[Sprinkle]


def mundane_commands(ctx: app.ArgparseApp):
    """Parser registration API."""
    bm_flags = ctx.get_shared_parser('bookmarks')
    dt_flags = ctx.get_shared_parser('drawtools')
    file_flags = ctx.get_shared_parser('file')
    glob_flags = ctx.get_shared_parser('glob')

    ctx.register_command(update, parents=[bm_flags])
    ctx.register_command(bounds, parents=[dt_flags, glob_flags])
    ctx.register_command(trim, parents=[bm_flags, dt_flags])
    ctx.register_command(cluster, parents=[file_flags])

    parser = ctx.register_command(donuts, parents=[dt_flags])
    parser.add_argument(
        '-c',
        '--count',
        action='store',
        type=int,
        required=True,
        help='Upper limit of portals per bite.')
    parser.add_argument(
        '-b',
        '--bites',
        action='store',
        type=int,
        default=sys.maxsize,
        help='Rough limit on the number of bites. (Default: %(default)s)')
    parser.add_argument(
        '-p',
        '--pattern',
        action='store',
        default='bm-donut-{count}-{bite:0{width}d}.json',
        help=(
            'Pattern used to name the output files.  Uses PEP 3101 formatting'
            ' strings with the following fields:  count, width, bite'
            ' (Default: %(default)s)'))

    parser = ctx.register_command(ellipse, parents=[dt_flags])
    parser.add_argument(
        '-c',
        '--count',
        action='store',
        type=int,
        required=True,
        help='The count of portals per ellipse.')
    parser.add_argument(
        '-n',
        '--number',
        action='store',
        type=int,
        default=sys.maxsize,
        help='Number of ellipse to compute. (Default: %(default)s)')
    parser.add_argument(
        '-p',
        '--pattern',
        action='store',
        default='bm-ellipse-{count}-{number:0{width}d}.json',
        help=(
            'Pattern used to name the output files.  Uses PEP 3101 formatting'
            ' strings with the following fields:  count, width, number'
            ' (Default: %(default)s)'))


def update(args: argparse.Namespace) -> int:
    """Update the directions between portals in a bookmarks file."""
    portals = bookmarks.load(args.bookmarks)
    _clean(args.dbc)
    _update_directions(args.dbc, portals)

    return 0


def bounds(args: argparse.Namespace) -> int:
    """Create a drawtools file outlining portals in multiple bookmarks files.

    A new boundary is created for each bookmarks file.

    Each boundary is given a unique color determined automatically.  They are
    known to be difficult to see against some IITC maps, so manual editing may
    be required.

    Hint: Useful for processing the output of the 'donuts' command.
    """
    collection_of_multi_points = list()
    for filename in itertools.chain(*args.glob):
        data = bookmarks.load(filename)
        points = list()
        for bookmark in list(data.values()):
            latlng = _latlng_str_to_floats(bookmark['latlng'])
            lnglat = (latlng[1], latlng[0])
            point = shapely.geometry.Point(lnglat)
            points.append(point)
        multi_points = shapely.geometry.MultiPoint(points)
        collection_of_multi_points.append(multi_points)
    drawtools.save_bounds(args.drawtools, collection_of_multi_points)

    return 0


def trim(args: argparse.Namespace) -> int:
    """Trim a bookmarks file to only include portals inside a boundary."""
    if shapely.speedups.available:
        shapely.speedups.enable()

    portals = bookmarks.load(args.bookmarks)
    collection = drawtools.load_polygons(args.drawtools)

    to_delete = set()
    for guid, portal in list(portals.items()):
        latlng = _latlng_str_to_floats(portal['latlng'])
        lnglat = (latlng[1], latlng[0])
        point = shapely.geometry.Point(lnglat)
        if not point.intersects(collection):
            to_delete.add(guid)
    for guid in to_delete:
        del portals[guid]

    if to_delete:
        print(('deleting:', to_delete))
        bookmarks.save(portals, args.bookmarks)

    return 0


def donuts(args: argparse.Namespace) -> int:
    """(V) Automatically group portals into COUNT sized bookmarks files.

    The idea is to provide a series of bookmarks that would be suitably
    sized groups for efficient capturing.

    Given a starting marker specified in the drawtools file, a circle
    (donut hole) that includes COUNT portals will be created.  The size
    of this hole will inform the size of concentric rings (donuts).

    The donuts will be broken down into bites that contain roughly COUNT
    portals.  The command will try to balance between between the number
    of portals in a bite and how big (in area) a bite would be.  For
    example, it will try to avoid having a bite be the entire donut
    because it covers a sparsely populated area.

    Hint: Use the 'bounds' and 'merge' commands to create interesting features
    to import into IITC.
    """
    dbc = args.dbc
    point = drawtools.load_point(args.drawtools)
    sprinkles = _load_sprinkles(point, dbc)
    sprinkles.sort(key=lambda x: x.distance)
    all_donuts, delta = _donuts(sprinkles, args.count)

    guids = frozenset(x.guid for x in all_donuts[0])
    result = dbc.session.query(
        database.geoalchemy2.functions.ST_ConvexHull(
            database.geoalchemy2.functions.ST_Union(
                database.PortalV2.point))).filter(
                    database.PortalV2.guid.in_(guids)).one()[0]

    max_area = dbc.session.scalar(result.ST_Area(1)) * FUDGE_FACTOR
    max_length = delta * 2
    print(f'{max_length=}')
    print(f'{max_area=}')

    bites = _bites(
        dbc, all_donuts, args.count, args.bites, max_length, max_area)
    print(f'There are {len(bites)} donut bites.')
    width = len(str(len(bites)))
    for bite_num, bite in enumerate(bites):
        filename = args.pattern.format(
            count=args.count, width=width, bite=bite_num)
        guids = frozenset(sprinkle.guid for sprinkle in bite)
        bookmarks.save_from_guids(guids, filename, dbc)

    return 0


def ellipse(args: argparse.Namespace) -> int:
    """(V) Find a number of n-ellipse containing portals.

    An n-ellipse is a generalization of the 2-foci ellipse and 1-focus ellipse
    (aka, the circle).  The idea is that the sum of distances from any given
    point on the edge to the foci is a constant.

    This implementation is much more simple than that: It will determine the
    total distance from a portal to the given foci and sort them.  That sorted
    listed list is broken up in groups of COUNT portals and turned into
    bookmarks files.

    Hint: Use the 'bounds' and 'merge' commands to create interesting features
    to import into IITC.
    """
    dbc = args.dbc
    points = drawtools.load_points(args.drawtools)
    portals = _load_portal_distances(points, dbc)
    width = len(str(args.number))
    for group_num, group in enumerate(_grouper(portals, args.count)):
        if group_num == args.number:
            break
        filename = args.pattern.format(
            count=args.count, width=width, number=group_num)
        print(f'min={group[0].distance} max={group[-1].distance}')
        guids = frozenset(portal.guid for portal in group)
        bookmarks.save_from_guids(guids, filename, dbc)

    return 0


def _load_portal_distances(
        points: database.geoalchemy2.elements.WKBElement,
        dbc: database.Database) -> Bite:
    """Load all portal information needed for donuts."""
    distance = operator.add(0, 0)
    for point in points:
        distance = operator.add(
            distance,
            database.geoalchemy2.functions.ST_Distance(
                point, database.PortalV2.point, 0))
    rows = dbc.session.query(
        database.PortalV2,
        distance.label('distance'),
    ).order_by('distance')
    return [
        Sprinkle(
            distance=row.distance,
            azimuth=0,
            guid=row.PortalV2.guid,
        ) for row in rows
    ]


def cluster(args: argparse.Namespace) -> int:  # pylint: disable=too-many-locals
    """Find clusters of portals together and save the results.

    The clustering results are saved into FILENAME.
    """
    dbc = args.dbc
    rtree_index = rtree.rtree_index(dbc)
    graph = pygraph.graph()  # type: ignore[name-defined] # pylint: disable=undefined-variable
    graph.add_nodes(iter(list(rtree_index.node_map.keys())))  # pylint: disable=no-member
    clusters = set()
    leaders = frozenset(
        row.guid for row in dbc.session.query(database.ClusterLeader))
    initial_leaders = leaders.copy()

    distance = START_DISTANCE
    while distance < MAX_DISTANCE:
        print(f'Looking for distance {distance}')
        to_clean = set()

        _add_edges(graph, rtree_index.index, rtree_index.node_map, distance)
        print('Extracting clusters from graph...')
        for new_cluster in _extract_clusters(graph):
            clusters.add((distance, new_cluster))
            to_clean.update(new_cluster)
        print('Clusters extracted.')

        _clean_clustered_points(
            graph, rtree_index.index, rtree_index.node_map, to_clean)
        distance *= 2

    clustered = _finalize(clusters, leaders, rtree_index)
    json.save(args.filename, clustered)
    final_leaders = {cluster['leader'] for cluster in clustered}
    old_leaders = initial_leaders.difference(final_leaders)
    new_leaders = final_leaders.difference(initial_leaders)
    logging.info('old_leaders: %s', old_leaders)
    logging.info('new_leaders: %s', new_leaders)
    for guid in old_leaders:
        dbc.session.query(database.ClusterLeader).filter(
            database.ClusterLeader.guid == guid).delete()

    for guid in new_leaders:
        db_cluster_leader = database.ClusterLeader(guid=guid)
        dbc.session.add(db_cluster_leader)
    dbc.session.commit()

    return 0


def _finalize(clusters, leaders, rtree_index):
    """Placeholder docstring for private function."""
    logging.info('_finalize: %d clusters', len(clusters))

    node_map_by_projected_coords = {
        node.projected_point.coords[0]: node
        for node in list(rtree_index.node_map.values())
    }
    clustered = list()
    for distance, nodes in clusters:
        clustered.append(
            _cluster_entry(
                distance, nodes, node_map_by_projected_coords, leaders,
                rtree_index))

    logging.info('_finalize: done')
    return clustered


def _cluster_entry(  # pylint: disable=too-many-locals,too-many-arguments
        distance, nodes, node_map_by_projected_coords, leaders,
        rtree_index):
    """Placeholder docstring for private function."""
    multi_point = shapely.geometry.MultiPoint(
        [rtree_index.node_map[idx].projected_point for idx in nodes])

    latlng_centroid = shapely.ops.transform(
        rtree_index.reverse_transform, multi_point.centroid)

    guids = set()
    guid_map = dict()
    for idx in nodes:
        guids.update(rtree_index.node_map[idx].guids)
        for guid in rtree_index.node_map[idx].guids:
            guid_map[guid] = idx
    possible_leaders = guids.intersection(leaders)

    if not possible_leaders:
        logging.info('finding new leader')
        local_rtree = rtree.rtree.index.Index(
            (idx, rtree_index.node_map[idx].projected_coords, None)
            for idx in nodes)

        leader_idx = list(
            local_rtree.nearest(
                (
                    multi_point.centroid.x, multi_point.centroid.y,
                    multi_point.centroid.x, multi_point.centroid.y),
                num_results=len(nodes) / 2))[-1]

        leader_guid = list(rtree_index.node_map[leader_idx].guids)[0]
    elif len(possible_leaders) == 1:
        logging.info('keeping existing leader: %s', possible_leaders)
        leader_guid = possible_leaders.pop()
    else:
        logging.info('selecting leader from: %s', possible_leaders)
        local_rtree = rtree.rtree.index.Index(
            (
                guid_map[guid],
                rtree_index.node_map[guid_map[guid]].projected_coords, None)
            for guid in possible_leaders)

        leader_idx = list(
            local_rtree.nearest(
                (
                    multi_point.centroid.x, multi_point.centroid.y,
                    multi_point.centroid.x, multi_point.centroid.y),
                num_results=len(nodes) / 2))[-1]

        leader_guid = list(rtree_index.node_map[leader_idx].guids)[0]

    logging.info('selected leader: %s', leader_guid)

    projected_hull = multi_point.convex_hull
    latlng_hull = (
        node_map_by_projected_coords[coord]
        for coord in projected_hull.exterior.coords)
    return {
        'area':
        projected_hull.area / 1000000,
        'centroid': {
            'lat': latlng_centroid.y,
            'lng': latlng_centroid.x,
        },
        'leader':
        leader_guid,
        # consider dropping density and calculate on client instead
        'density':
        len(nodes) / projected_hull.area * 1000000,
        'distance':
        distance,
        'hull': [
            {
                'lat': node.latlng_point.y,
                'lng': node.latlng_point.x,
            } for node in latlng_hull
        ],
        'perimeter':
        projected_hull.exterior.length,
        'portals':
        sorted(guids),
    }


def _clean_clustered_points(graph, index, node_map, new_cluster):
    """Placeholder docstring for private function."""
    logging.info('_clean_clustered_points: %d nodes', len(new_cluster))
    print('Cleaning out clustered points...')
    for node_index in new_cluster:
        node = node_map[node_index]
        index.delete(node_index, node.projected_coords)
        graph.del_node(node_index)
    logging.info(
        '_clean_clustered_points: points left in graph: %d',
        len(graph.nodes()))


def _extract_clusters(graph):
    """Placeholder docstring for private function."""
    logging.info('entered _extract_clusters')
    visited = set()
    for node in graph.nodes():
        if node in visited:
            continue
        visited.add(node)
        other_nodes = frozenset(pytraversal.traversal(graph, node, 'pre'))  # pylint: disable=undefined-variable
        visited.update(other_nodes)
        if len(other_nodes) >= MINIMAL_CLUSTER_SIZE:
            yield other_nodes
    logging.info('leaving _extract_clusters')


def _add_edges(graph, index, node_map_by_index, max_distance):  # pylint: disable=too-many-locals
    """Placeholder docstring for private function."""
    logging.info('_add_edges for %d', max_distance)
    node_count = 0
    edge_count = 0
    result_limit = 1
    for node_index in graph.nodes():
        node_count += 1
        if node_count % 10000 == 0:
            print(('at node count', node_count))
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
                    graph.add_edge(edge)
                    edge_count += 1

    logging.info('_add_edges: edges added: %d', edge_count)


def _bites(  # pylint: disable=too-many-arguments
        dbc: database.Database, all_donuts: list[Bite], count: int,
        max_bites: int, max_length: float, max_area: float) -> list[Bite]:
    """Divide the donuts into bite-sized morsels (e.g., COUNT portals)."""
    all_bites: list[Bite] = list()
    _order_sprinkles_on_donuts(all_donuts)
    for real_donut in all_donuts:
        dist_cache: DistanceCache = dict()
        donut = list(real_donut)
        while donut:
            bite = _bite(dbc, donut[:count], max_length, max_area, dist_cache)
            donut = donut[len(bite):]
            all_bites.append(bite)
        if len(all_bites) > max_bites:
            break

    return all_bites


def _get_wkb_to_point_map(dbc, ring):
    """Map stable WKB to Geometry for easier caching."""
    dss = dbc.session.scalar
    num_points = dss(ring.ST_NPoints()) - 1
    wkb_to_point = dict()
    for entry in range(num_points):
        point = ring.ST_PointN(entry + 1)
        wkb_to_point[dss(point)] = point
    return wkb_to_point


def _get_distances(
        dbc: database.Database, ring: database.geoalchemy2.types.Geometry,
        cache: DistanceCache) -> list[float]:
    """Calculate the distances between every sprinkle."""
    dss = dbc.session.scalar
    num_points = dss(ring.ST_NPoints()) - 1
    wkb_to_point = _get_wkb_to_point_map(dbc, ring)

    distances = [0.0]
    wkbs = list(wkb_to_point.keys())
    for x_off in range(num_points):
        wkb_x = wkbs[x_off]
        point_x = wkb_to_point[wkb_x]
        for y_off in range(x_off + 1, num_points):
            wkb_y = wkbs[y_off]
            key = (wkb_x, wkb_y)
            if key not in cache:
                cache[key] = dss(point_x.ST_Distance(wkb_to_point[wkb_y], 0))
            distances.append(cache[key])
    return distances


def _bite(
        dbc: database.Database, donut: Bite, max_length: float,
        max_area: float, cache: DistanceCache) -> Bite:
    """Given a donut, return a bite that is not a choking hazard."""
    dss = dbc.session.scalar
    guids = frozenset(x.guid for x in donut)
    db_points = dbc.session.query(
        database.geoalchemy2.functions.ST_Collect(
            database.PortalV2.point)).filter(
                database.PortalV2.guid.in_(guids)).one()[0]

    hull = db_points.ST_ConvexHull()
    ring = hull.ST_ExteriorRing()
    num_ring_points = dss(ring.ST_NPoints())

    good = True

    if num_ring_points is not None:
        area = dss(hull.ST_Area(True))
        if area > max_area:
            good = False
        else:
            distance = max(_get_distances(dbc, ring, cache))
            if distance > max_length:
                good = False

    if good:
        return donut

    # Try again with one less sprinkle
    return _bite(dbc, donut[:-1], max_length, max_area, cache)


def _order_sprinkles_on_donuts(all_donuts: list[Bite]):
    """Sort the sprinkles by azimuth on each donut."""
    for donut in all_donuts:
        # We do not want the bites to align along the 0th azimuth (north), so
        # we use the first sprinkle we find on the donut and order everything
        # relative to it.
        start = donut[0].azimuth
        for sprinkle in donut:
            if sprinkle.azimuth < start:
                sprinkle.azimuth += math.pi * 2
        donut.sort(key=lambda sprinkle: sprinkle.azimuth)


def _donuts(all_sprinkles: Bite, count: int) -> tuple[list[Bite], float]:
    """Each donut should have at least count sprinkles on it."""
    list_of_donuts = list()
    delta = all_sprinkles[count].distance
    radius = 0.0
    while all_sprinkles:
        donut: Bite = list()
        # Keep making current donut bigger until it has at least "count"
        # sprinkles on it.
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
        list_of_donuts.append(donut)
    return list_of_donuts, delta


def _load_sprinkles(
        center_point: database.geoalchemy2.elements.WKBElement,
        dbc: database.Database) -> Bite:
    """Load all portal information needed for donuts."""
    rows = dbc.session.query(
        database.PortalV2,
        database.geoalchemy2.functions.ST_Distance(
            center_point, database.PortalV2.point, 0).label('distance'),
        database.geoalchemy2.functions.ST_Azimuth(
            center_point, database.PortalV2.point).label('azimuth'),
    )
    return [
        Sprinkle(
            distance=row.distance,
            azimuth=row.azimuth,
            guid=row.PortalV2.guid,
        ) for row in rows
    ]


def _portal_combos(portals):
    """Placeholder docstring for private function."""
    for begin_portal in list(portals.values()):
        for end_portal in list(portals.values()):
            if begin_portal['guid'] != end_portal['guid']:
                for mode in ('walking', 'driving'):
                    yield begin_portal, end_portal, mode


def _grouper(iterable, size):
    """Group iterable into batches of size items."""
    filler = dict()
    args = (iter(iterable),) * size
    for group in itertools.zip_longest(*args, fillvalue=filler):
        yield tuple(item for item in group if item is not filler)


def _update_directions(dbc: database.Database, portals: bookmarks.Portals):
    """Placeholder docstring for private function."""
    _update_paths(dbc, portals)
    _update_path_legs(dbc, portals)


def _update_paths(dbc: database.Database, portals: bookmarks.Portals):  # pylint: disable=too-many-locals
    """Placeholder docstring for private function."""
    now = time.time()
    combo_groups = _grouper(_portal_combos(portals), 64)
    for combo_group in combo_groups:
        filtered_combo_group = [x for x in combo_group if x is not None]
        needed = set()
        queries = collections.defaultdict(set)
        for begin_portal, end_portal, mode in filtered_combo_group:
            needed.add((begin_portal['latlng'], end_portal['latlng'], mode))
            queries[mode].add(begin_portal['latlng'])
        for mode, begin_portals in list(queries.items()):
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


def _update_path_legs(dbc: database.Database, portals: bookmarks.Portals):
    """Placeholder docstring for private function."""
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
    """Placeholder docstring for private function."""
    path_ids = list(path_ids)
    random.shuffle(path_ids)
    print(f'Paths to check: {len(path_ids)}')
    for count, path_id in enumerate(path_ids):
        _ensure_path_legs_by_path_id(dbc, count, path_id)


def _ensure_path_legs_by_path_id(dbc, count, path_id):
    """Placeholder docstring for private function."""
    db_path = dbc.session.query(database.Path).get(path_id)

    print(
        f'{count:4} path_id: {path_id:4}|{db_path.begin_latlng:23}'
        f'|{db_path.end_latlng:23}')

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
                print(f'There is a hole for path {path_id}.  Clearing.')
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
    """Placeholder docstring for private function."""
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
            db_leg = database.Leg(
                begin_latlng=google_leg.begin_latlng,
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
    """Placeholder docstring for private function."""
    google_leg = google.directions(begin, end, mode)
    crow_flies = _distance(begin, end)
    if mode == 'driving' and (crow_flies < 120 or google_leg.duration < 30):
        google_leg = google.directions(begin, end, 'walking')

    if _distance(google_leg.begin_latlng, google_leg.end_latlng) < 10:
        google_leg.begin_latlng = begin
        google_leg.end_latlng = end
        google_leg.mode = 'walking'
        google_leg.duration = crow_flies  # seems like a good guess
        google_leg.polyline = str(
            google.encode_polyline(
                (_latlng_str_to_floats(begin), _latlng_str_to_floats(end))))

    fmt = '{state:7}: {begin:23} {end:23} {mode:7} {distance:5}'
    print(
        fmt.format(
            state='wanted',
            begin=begin,
            end=end,
            mode=mode,
            distance=crow_flies))
    print(
        fmt.format(
            state='got',
            begin=google_leg.begin_latlng,
            end=google_leg.end_latlng,
            mode=google_leg.mode,
            distance=_distance(
                google_leg.begin_latlng, google_leg.end_latlng)))

    return google_leg


def _clean(dbc: database.Database):
    """Clean out old cached data."""
    now = time.time()
    oldest_allowed = now - MAX_AGE
    rows = dbc.session.query(
        database.Leg).filter(database.Leg.date < oldest_allowed)
    for row in rows:
        print('Delete ', row)
    rows = dbc.session.query(
        database.Path).filter(database.Path.date < oldest_allowed)
    for row in rows:
        print('Delete ', row)
    dbc.session.commit()


def _distance(begin, end):
    """Placeholder docstring for private function."""
    geod = pyproj.Geod(ellps='WGS84')
    blat, blng = _latlng_str_to_floats(begin)
    elat, elng = _latlng_str_to_floats(end)
    fwd, rev, dist = geod.inv(blng, blat, elng, elat)
    del fwd, rev
    return dist


def _latlng_str_to_floats(latlng_as_str):
    """Placeholder docstring for private function."""
    lat, lng = latlng_as_str.split(',')
    return float(lat), float(lng)
