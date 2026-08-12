"""Functions for working with IITC drawtools files."""
from __future__ import annotations

import colorsys
import typing

import pyproj
import shapely  # type: ignore[import]

from ingress import database
from ingress import json

if typing.TYPE_CHECKING:  # pragma: no cover
    import argparse

    from mundane import app

    from ingress import geo

sqla = database.sqlalchemy

Statement: typing.TypeAlias = sqla.sql.selectable.Select


class Error(Exception):
    """Base module exception."""


def mundane_shared_flags(ctx: app.ArgparseApp):
    """Register shared flags."""
    parser = ctx.safe_new_shared_parser('drawtools')
    parser.add_argument(
        '-d',
        '--drawtools',
        action='store',
        required=True,
        help='IITC drawtools json file to use'
    )


def save_bounds(
    dbc: database.Database, filename: str, collections: list[Statement]
):
    """Save the hulls of collections of points in drawtools format."""
    hulls = list()

    for index, stmt in enumerate(collections):
        collection = stmt.cte('collection', recursive=True)
        buffered = sqla.select(
            sqla.case(
                (
                    collection.c.geom.ST_NumGeometries() < 3,
                    collection.c.geom.ST_Buffer(0.00005, 3),
                ),
                else_=collection.c.geom
            ).label('geom')
        ).select_from(collection).cte('buffered')
        hull = sqla.select(
            buffered.c.geom.ST_ConvexHull().ST_ExteriorRing().label('geom')
        ).cte('hull')
        n_geom = sqla.select(sqla.literal(1).label('n'), hull.c.geom).where(
            hull.c.geom.ST_PointN(1) != sqla.null()
        ).cte(
            'n_geom', recursive=True
        )
        n_geom = n_geom.union_all(
            sqla.select(n_geom.c.n + 1, n_geom.c.geom).where(
                n_geom.c.geom.ST_PointN(n_geom.c.n + 1) != sqla.null()
            )
        )
        points = sqla.select(
            n_geom.c.n,
            n_geom.c.geom.ST_PointN(n_geom.c.n).label('geom')
        ).cte('points')
        stmt = sqla.select(
            points.c.geom.ST_Y().label('lat'),
            points.c.geom.ST_X().label('lng')
        )

        lat_lngs = list(
            dict(row) for row in dbc.session.execute(stmt).mappings()
        )

        if lat_lngs:
            hulls.append({
                'type': 'polygon',
                'latLngs': lat_lngs,
            })

    for index, hull in enumerate(hulls):
        color = _rainbow(index / (len(hulls) - 1))
        hull['color'] = f'#{color}'

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


def load_point(filename: str) -> database.WKT:
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
            f' has {num_points} elements instead'
        )

    return list(points)[0]


def load_points(filename: str) -> frozenset[database.WKT]:
    """Find a collection of points from a drawtools file.

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


def _rainbow(hue: float) -> str:
    """Return a color along a rainbow-like continuum.

    See https://www.colorcet.com/userguide#rainbow on why this is bad.

    Args:
      hue: Some point in the range [0.0, 1.0].

    Returns:
      A hex-number as a string.
    """
    if hue < 0.0 or hue > 1.0:
        raise Error(f'out of range: {hue}')
    red, grn, blu = colorsys.hsv_to_rgb(hue * 5 / 6, 1, 1)

    red_ = round(red * 255)
    grn_ = round(grn * 255)
    blu_ = round(blu * 255)
    result = f'#{red_:02x}{grn_:02x}{blu_:02x}'
    return result
