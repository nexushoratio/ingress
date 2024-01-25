"""RTree functions that are shared between modules."""

import collections
import functools
import logging

import attr
import pyproj
import rtree
import shapely

from ingress import database


def rtree_index(dbc):
    return _rtree_index(_node_map(dbc))


def _rtree_index(node_map_by_wkt):
    """Placeholder docstring for private function."""
    # First, find a good centroid to use for a projection, then use that
    # projection for the index
    logging.info('_rtree_index: nodes: %d', len(node_map_by_wkt))
    nodes = list(node.latlng_point for node in list(node_map_by_wkt.values()))
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
        stere_multi_points = shapely.ops.transform(
            forward_transform, latlng_multi_points)
        centroid = shapely.ops.transform(
            reverse_transform, stere_multi_points.centroid)
        new_centroid = _closest_point(centroid, latlng_multi_points)

    logging.info('projecting around %s', new_centroid)
    node_map_by_index = _node_map_by_index(
        enumerate(zip(stere_multi_points, latlng_multi_points)),
        node_map_by_wkt)

    logging.info('building rtree index')
    index = rtree.index.Index(
        (idx, node.projected_coords, None)
        for idx, node in list(node_map_by_index.items()))
    logging.info('built rtree index')
    return RtreeIndex(
        index=index,
        forward_transform=forward_transform,
        reverse_transform=reverse_transform,
        node_map=node_map_by_index)


def _node_map(dbc):
    """Create a mapping from latlngs to portal guids."""
    logging.info('entered _node_map')
    node_map = collections.defaultdict(NodeData)
    for db_portal in dbc.session.query(database.Portal):
        point = _latlng_str_to_point(db_portal.latlng)
        node = node_map[point.wkt]
        node.latlng_point = point
        node.latlng_point_wkt = point.wkt
        node.guids.add(db_portal.guid)
    logging.info('_node_map: nodes mapped: %d', len(node_map))
    return node_map


@attr.s
class NodeData:  # pylint: disable=missing-docstring,too-few-public-methods
    latlng_point = attr.ib(init=False, default=None)
    latlng_point_wkt = attr.ib(init=False, default=None)
    projected_point = attr.ib(init=False, default=None)
    projected_point_wkt = attr.ib(init=False, default=None)
    projected_coords = attr.ib(init=False, default=None)
    # We use a set for guids because we may have two portals at the same
    # latlng.
    guids = attr.ib(init=False, default=attr.Factory(set))


def _latlng_str_to_point(latlng_as_str):
    """Placeholder docstring for private function."""
    lat, lng = _latlng_str_to_floats(latlng_as_str)
    return shapely.geometry.Point(lng, lat)


def _latlng_str_to_floats(latlng_as_str):
    """Placeholder docstring for private function."""
    lat, lng = latlng_as_str.split(',')
    return float(lat), float(lng)


def _closest_point(target, points):
    """Placeholder docstring for private function."""
    # Find a known point that is the closest to the target point
    logging.info('_closest_point: near %s', target)

    @attr.s
    class DistancePoint:  # pylint: disable=missing-docstring,too-few-public-methods
        distance = attr.ib()
        point = attr.ib()

    geod = pyproj.Geod(ellps='WGS84')
    tlat = target.y
    tlng = target.x
    distances = (
        DistancePoint(
            distance=geod.inv(point.x, point.y, tlng, tlat)[2], point=point)
        for point in points)
    result = min(distances, key=lambda x: x.distance)
    logging.info('_closest_point: found %s', result)
    return result.point


def _node_map_by_index(index_pair, node_map_by_wkt):
    """Placeholder docstring for private function."""
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


@attr.s
class RtreeIndex:  # pylint: disable=missing-docstring,too-few-public-methods
    index = attr.ib()
    forward_transform = attr.ib()
    reverse_transform = attr.ib()
    node_map = attr.ib()
