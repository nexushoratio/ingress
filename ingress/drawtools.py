"""Functions for working with IITC drawtools files."""
from __future__ import annotations

import typing

import pyproj
import shapely  # type: ignore[import]

from ingress import database
from ingress import json

if typing.TYPE_CHECKING:  # pragma: no cover
    import argparse

    from mundane import app


def mundane_shared_flags(ctx: app.ArgparseApp):
    """Register shared flags."""
    parser = ctx.new_shared_parser('drawtools')
    if parser:
        parser.add_argument(
            '-d',
            '--drawtools',
            action='store',
            required=True,
            help='IITC drawtools json file to use')


def save_bounds(filename, collections):
    """Save the hull of MultiPoints instances in drawtools format."""
    hulls = list()
    color = 256 * 256 * 256
    stride = color // (len(collections) + 1)
    for index, collection in enumerate(collections, start=1):
        if len(collection.geoms) < 3:
            # give points and lines a bit of area
            collection = collection.buffer(0.0005, resolution=1)
        color = stride * index

        hull_shapely = collection.convex_hull.exterior.coords
        hull = [{'lng': point[0], 'lat': point[1]} for point in hull_shapely]
        hulls.append(
            {
                'type': 'polygon',
                'color': f'#{color:06x}',
                'latLngs': hull
            })
    json.save(filename, hulls)


def load_polygons(filename):
    """Load items from a drawtools file into a geometry.MultiPolygon."""
    outlines = json.load(filename)
    polygons = list()
    for outline in outlines:
        typ = outline['type']
        if typ == 'polygon':
            points = [
                (point['lng'], point['lat']) for point in outline['latLngs']
            ]
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
            polygons.append(shapely.geometry.Polygon(points))
        else:
            raise TypeError(f'{typ} is a type not yet handled.')

    return shapely.geometry.MultiPolygon(polygons)


def load_point(filename: str) -> database.geoalchemy2.elements.WKTElement:
    """Find a singular point from a drawtools file.

    Args:
      filename: name of the file

    Returns:
      The singular point.
    """
    points = load_points(filename)
    num_points = len(points)
    if num_points != 1:
        raise RuntimeError(
            f'{filename} should have one element;'
            f' has {num_points} elements instead')

    return list(points)[0]


def load_points(
        filename: str) -> frozenset[database.geoalchemy2.elements.WKTElement]:
    """Find a collection of point from a drawtools file.

    Args:
      filename: name of the file

    Returns:
      The points.
    """
    common_point_types = ('circle', 'marker')
    drawing = json.load(filename)
    points = set()
    for element in drawing:
        typ = element['type']
        if typ in common_point_types:
            latlng = element['latLng']
            points.add(database.latlng_dict_to_point(latlng))
        else:
            raise TypeError(f'"{typ}" is a type not yet handled.')

    return frozenset(points)
