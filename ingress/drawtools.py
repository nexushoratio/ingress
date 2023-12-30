"""Functions for working with IITC drawtools files."""

import pyproj
import shapely

from ingress import json


def mundane_shared_flags(ctx: 'mundane.ArgparserApp'):
    """Register shared flags."""
    parser = ctx.new_shared_parser('drawtools')
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
    stride = color / (len(collections) + 1)
    for index, collection in enumerate(collections, start=1):
        if len(collection) < 3:
            # give points and lines a bit of area
            collection = collection.buffer(0.0005, resolution=1)
        color = stride * index

        hull_shapely = collection.convex_hull.exterior.coords
        hull = [{'lng': point[0], 'lat': point[1]} for point in hull_shapely]
        hulls.append(
            {
                'type': 'polygon',
                'color': '#%06x' % color,
                'latLngs': hull
            })
    json.save(filename, hulls)


def load_polygons(filename):
    """Load items from a drawtools file into a shapely.geometry.MultiPolygon."""
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
            raise Exception('%s is a type not yet handled.' % typ)

    return shapely.geometry.MultiPolygon(polygons)


def load_point(filename):
    """Find a singular point from a drawtools file.

    Args:
      filename: str, name of the file

    Returns:
      shapely.geometry.Point
    """
    common_point_types = ('circle', 'marker')
    drawing = json.load(filename)
    if len(drawing) != 1:
        raise Exception(
            '%s should have one element; has %d elements instead' %
            (filename, len(drawing)))
    element = drawing[0]
    typ = element['type']
    if typ in common_point_types:
        latlng = element['latLng']
        lat = latlng['lat']
        lng = latlng['lng']
    else:
        raise Exception('%s is a type not yet handlded.' % typ)

    point = shapely.geometry.Point(lng, lat)
    return point
