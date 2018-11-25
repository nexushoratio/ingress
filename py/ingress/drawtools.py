"""Functions for working with IITC drawtools files."""

import pyproj
import shapely

from ingress import json


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


def save_bounds(filename, collection):
    """Save the hull of a MultiPoints instance in drawtools format."""
    hull_shapely = collection.convex_hull.exterior.coords

    hull = [{'lng': point[0], 'lat': point[1]} for point in hull_shapely]
    json.save(filename, [{'type': 'polygon', 'latLngs': hull}])


def load_polygons(filename):
    """Load items from a drawtools file into a shapely.geometry.MultiPolygon."""
    outlines = json.load(filename)
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
            polygons.append(shapely.geometry.Polygon(points))
        else:
            raise Exception('%s is a type not yet handled.' % typ)

    return shapely.geometry.MultiPolygon(polygons)
