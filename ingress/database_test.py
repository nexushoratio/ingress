"""Tests for database.py"""

# pylint: disable=protected-access

import argparse
import pathlib
import sqlite3
import unittest

from mundane import app

from ingress import database
from ingress import test_helper


class MundaneGlobalFlagsTest(unittest.TestCase):

    def test_basic(self):
        my_app = app.ArgparseApp()

        database.mundane_global_flags(my_app)
        flags = vars(my_app.parser.parse_args([]))

        self.assertIn('db_dir', flags)
        self.assertIn('db_name', flags)


class ConversionsTest(unittest.TestCase):

    def test_latlng_via_point(self):
        tetrahelix = '37.423521,-122.089649'

        result = database._point_to_latlng(
            database._latlng_to_point(tetrahelix)
        )

        self.assertEqual(tetrahelix, result)

    def test_latlng_dict_via_point(self):
        tetrahelix = '37.423521,-122.089649'
        # E.g., as seen in drawtool
        latlng = {
            "lat": 37.423521,
            "lng": -122.089649,
        }

        result = database._point_to_latlng(
            database.latlng_dict_to_point(latlng)
        )

        self.assertEqual(tetrahelix, result)


class InitDbTest(unittest.TestCase):

    def test_args(self):
        # Create dbc just to generate filenames
        dbc = test_helper.database_connection(self)
        args = argparse.Namespace(
            db_dir=dbc._directory, db_name=dbc._filename
        )

        self.assertTrue(hasattr(args, 'db_dir'))
        self.assertTrue(hasattr(args, 'db_name'))
        self.assertFalse(hasattr(args, 'dbc'))

        database.init_db(args)

        self.assertFalse(hasattr(args, 'db_dir'))
        self.assertFalse(hasattr(args, 'db_name'))
        self.assertTrue(hasattr(args, 'dbc'))

        self.assertIsInstance(args.dbc, database.Database)  # pylint: disable=no-member


class DatabaseTest(unittest.TestCase):

    def test_deferred_session(self):
        dbc = test_helper.database_connection(self)
        db_path = pathlib.Path(dbc._directory, dbc._filename)

        self.assertFalse(db_path.exists())
        self.assertIsInstance(dbc.session, database.sqlalchemy.orm.Session)
        self.assertTrue(db_path.exists())

    def test_portals_v2_migration(self):
        dbc = test_helper.database_connection(self)
        db_path = pathlib.Path(dbc._directory, dbc._filename)
        conn = sqlite3.connect(db_path)
        dbc._connect(dbapi_connection=conn)
        # Darn, unable to use the 'CreateTable' output here because GEOMETRY.
        ddl = """
CREATE TABLE portals (
    guid VARCHAR NOT NULL,
    label VARCHAR NOT NULL,
    first_seen INTEGER NOT NULL,
    last_seen INTEGER NOT NULL,
    latlng GEOMETRY,
    CONSTRAINT pk_portals PRIMARY KEY (guid)
)
"""
        conn.execute(ddl)
        conn.execute(
            'SELECT RecoverGeometryColumn(?,?,?,?,?)',
            ('portals', 'latlng', 4326, 'POINT', 'XY')
        )
        data = [
            (
                '1e4669c234ad492e9dfa7b0a2da05cde.16',
                'Google Volleyball Sand Court', 0, 0, -122.085126, 37.421963
            ),
            (
                '09d5d1e149014c70ba3154fe3421e2a6.12', 'Tetrahelix', 0, 0,
                -122.089649, 37.423521
            ),
            (
                '9f2eaaa0c1ae4204a2ba5edd46ad4c95.12', "Cupid's Span", 0, 0,
                -122.390014, 37.791541
            )
        ]
        conn.executemany(
            'INSERT INTO portals VALUES(?,?,?,?,MakePoint(?,?,4326))', data
        )
        conn.commit()
        expected = frozenset(str(item[5]) for item in data)

        stmt = database.sqlalchemy.select(database.PortalV2)
        actual = frozenset(
            row.PortalV2.lat for row in dbc.session.execute(stmt)
        )

        self.assertEqual(actual, expected)


if __name__ == '__main__':  # pragma: no cover
    unittest.main()
