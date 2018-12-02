"""Deal with ZIP Code Tabulate Areas.

The ZCTA information is huge.  It takes a long time to process some
aspects of it, so it is done ahead of time.  And that preprocessed
data itself takes a long time to load.

Each area consists of one or my polygons, and each polygon can have
one or more holes in it.  The slow processing it figuring out which
polygons are shells and which are holes.

Each area is turned into a MULTIPOLYGON then collected based up the
first two digits of the code.  Each collection is saved by itself is
mapped by the full code.  Each collection is also used to generate a
convex hull for that collection and all of those hulls are saved into
an index.

A point is first looked up in the index to figure out which one or
more collection it might belong to, then those collections are
searched.

Currently collecting and indexing is done using json files.
"""
import collections
import logging

import os.path

import shapefile
import shapely.geometry
import shapely.ops
import shapely.wkt
import shapely.speedups

from ingress import json


class Zcta(object):
    """Deal with all things ZCTA."""
    BASE_PATH = (os.sep, 'home', 'nexus', 'zcta')
    SHAPEFILE = 'cb_2017_us_zcta510_500k'
    INDEX_JSON = 'index.json'

    def __init__(self):
        if shapely.speedups.available:
            shapely.speedups.enable()
        self._codes = list()
        self._groups_loaded = set()
        self._code_index = None

    # Maybe make this importer a class on its own
    def import_from_shapefile(self):  # pylint: disable=too-many-locals
        """Start with a ZCTA shapefile and divvy it up."""
        multi_polygons_by_code = collections.defaultdict(dict)

        file_name = self._full_path(self.SHAPEFILE)
        logging.info('Importing from %s', file_name)
        shapefile_reader = shapefile.Reader(file_name)
        logging.info('%d area', shapefile_reader.numRecords)
        print shapefile_reader.numRecords

        for record_number in xrange(shapefile_reader.numRecords):
            shells = list()
            holes = list()
            shape_record = shapefile_reader.shapeRecord(record_number)
            shape = shape_record.shape
            code = shape_record.record[0]
            indices = list(shape.parts) + [None]
            for part in range(len(shape.parts)):
                start = indices[part]
                end = indices[part + 1]
                polygon = shapely.geometry.Polygon(shape.points[start:end])

                if polygon.exterior.is_ccw:
                    holes.append(polygon)
                else:
                    shells.append(polygon)

            new_shells = list()
            for shell in shells:
                new_holes = list()
                for hole in holes:
                    if hole.within(shell):
                        new_holes.append(hole)
                new_shell = shapely.geometry.Polygon(
                    shell.exterior.coords,
                    [x.exterior.coords for x in new_holes])
                new_shells.append(new_shell)
            multi_polygon = shapely.geometry.MultiPolygon(new_shells)
            multi_polygons_by_code[code[:2]][code] = multi_polygon.wkt

        hulls_by_code = dict()
        for code, multi_polygons in multi_polygons_by_code.iteritems():
            basename = '%s.json' % code
            json.save(self._full_path(basename), multi_polygons)
            hulls_by_code[code] = shapely.ops.unary_union([
                shapely.wkt.loads(multi_polygon_wkt)
                for multi_polygon_wkt in multi_polygons.itervalues()
            ]).convex_hull.wkt
        json.save(self._full_path(self.INDEX_JSON), hulls_by_code)

    def code_from_latlng(self, latlng):
        """Given a latlng string, find the associated code."""
        lat, lng = latlng.split(',')
        point = shapely.geometry.Point(float(lng), float(lat))
        return self.code_from_point(point)

    def code_from_point(self, point):
        """Given a shapely Point, find the associated code."""
        code = self._point_in_any_code(point)
        if code is None:
            self._load_group(point)
            code = self._point_in_any_code(point)
        if code is None:
            logging.info('Unable to find code for %s', point)
            code = 'Unknown'
        return code

    def _point_in_any_code(self, point):
        for index, entry in enumerate(self._codes):
            code, area = entry
            if point.intersects(area):
                # Move to the front
                if index > 275:
                    self._codes.pop(index)
                    self._codes.insert(0, entry)
                return code

    def _load_group(self, point):
        if self._code_index is None:
            self._load_code_index()

        for code, polygon in self._code_index.iteritems():
            if code not in self._groups_loaded:
                if point.intersects(polygon):
                    self._groups_loaded.add(code)
                    basename = '%s.json' % code
                    group = json.load(self._full_path(basename))
                    for key, value in group.iteritems():
                        area = shapely.wkt.loads(value)
                        self._codes.append((key, area))

    def _load_code_index(self):
        wkt = json.load(self._full_path(self.INDEX_JSON))
        self._code_index = dict()
        for code, polygon in wkt.iteritems():
            self._code_index[code] = shapely.wkt.loads(polygon)

    def _full_path(self, file_name):
        path_name = self.BASE_PATH + tuple([file_name])
        return os.path.join(*path_name)
