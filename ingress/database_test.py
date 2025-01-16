"""Tests for database.py"""

# pylint: disable=protected-access

import argparse
import contextlib
import io
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


class ReprMixinTest(unittest.TestCase):

    def test_basic(self):
        addr_type = database.AddressType(type='test', note='A note.')

        self.assertEqual(
            str(addr_type),
            "AddressType(type='test', visibility=None, note='A note.')"
        )

    def test_exclude(self):
        addr = database.Address(
            address='123 Main Street, Home Town, DC',
            latlng='12.34,-56.78',
            date=1
        )

        # Note that "lat" and "lng" are excluded
        self.assertEqual(
            str(addr), (
                "Address(latlng='12.34,-56.78',"
                " address='123 Main Street, Home Town, DC', date=1)"
            )
        )


class PortalV2Test(unittest.TestCase):

    def test_iitc(self):
        tetrahelix = {
            "first_seen": 1,
            "guid": "09d5d1e149014c70ba3154fe3421e2a6.12",
            "label": "Tetrahelix",
            "last_seen": 2,
            "latlng": "37.423521,-122.089649"
        }
        portal = database.PortalV2(**tetrahelix)

        result = portal.to_iitc()

        self.assertEqual(result, tetrahelix)


class UuidMixinTest(unittest.TestCase):

    def test_default(self):
        folder = database.BookmarkFolder()

        self.assertTrue(folder.uuid)

    def test_provided(self):
        folder = database.BookmarkFolder(uuid='abc')

        self.assertEqual(folder.uuid, 'abc')


class DatabaseTest(unittest.TestCase):

    def test_repr(self):
        dbc = test_helper.database_connection(self)
        mee = self.id()

        self.assertRegex(
            str(dbc), rf'Database\(directory=.*, filename={mee}\)'
        )

    def test_deferred_session(self):
        dbc = test_helper.database_connection(self)
        db_path = pathlib.Path(dbc._directory, dbc._filename)

        self.assertFalse(db_path.exists())
        self.assertIsInstance(dbc.session, database.sqlalchemy.orm.Session)
        self.assertTrue(db_path.exists())

    def test_sanity_check_with_auto_drop(self):
        dbc = test_helper.database_connection(self)
        db_path = pathlib.Path(dbc._directory, dbc._filename)
        conn = sqlite3.connect(db_path)
        dbc._connect(dbapi_connection=conn)

        ddl = 'CREATE TABLE cluster_leaders (guid VARCHAR NOT NULL)'
        conn.execute(ddl)

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            stmt = database.sqlalchemy.select(database.ClusterLeader)
            dbc.session.execute(stmt)

        self.assertIn('dropping: cluster_leaders', stdout.getvalue())

    def test_sanity_check_without_auto_drop(self):
        dbc = test_helper.database_connection(self)
        db_path = pathlib.Path(dbc._directory, dbc._filename)
        conn = sqlite3.connect(db_path)
        dbc._connect(dbapi_connection=conn)

        ddl = 'CREATE TABLE portals (guid VARCHAR NOT NULL)'
        conn.execute(ddl)

        with self.assertRaisesRegex(database.Error,
                                    'Unhandled tables with differences'):
            stmt = database.sqlalchemy.select(database.ClusterLeader)
            dbc.session.execute(stmt)

    def test_spatialite_initialized(self):
        # When the database is first created, spatialite is also initialized
        # which causes some issues with geoalchemy2 and computed columns that
        # need to be handled.
        dbc = test_helper.database_connection(self)
        self.assertFalse(dbc._spatialite_initialized)
        self.assertTrue(dbc.session)
        self.assertTrue(dbc._spatialite_initialized)
        dbc.dispose()

        # But, after the first time, no need for the special handling
        self.assertTrue(dbc.session)
        self.assertFalse(dbc._spatialite_initialized)

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

    def test_optimize_output(self):
        dbc = test_helper.database_connection(self)
        dbc.session.add(
            database.PortalV2(
                guid='guid',
                label='label',
                first_seen=0,
                last_seen=0,
                latlng='123,45'
            )
        )
        dbc.session.commit()

        stmt = database.sqlalchemy.select(
            database.PortalV2
        ).where(database.PortalV2.first_seen < 1)
        dbc.session.scalars(stmt)
        dbc.dispose()

        db_path = pathlib.Path(dbc._directory, dbc._filename)
        conn = sqlite3.connect(db_path)

        tables = [
            row[0]
            for row in conn.execute('SELECT DISTINCT(tbl) FROM sqlite_stat1')
        ]

        self.assertIn('v2_portals', tables)

    def test_dispose_resets_session(self):
        dbc = test_helper.database_connection(self)

        orig_session = dbc.session
        self.assertEqual(dbc.session, orig_session)

        dbc.dispose()
        self.assertNotEqual(dbc.session, orig_session)

    def test_dispose_before_session_does_not_crash(self):
        dbc = test_helper.database_connection(self)

        dbc.dispose()
        dbc.dispose()

    def test_frag_check_short_connection(self):
        dbc = test_helper.database_connection(self)

        self.assertTrue(dbc.session)
        dbc.dispose()

        dbc = database.Database(dbc._directory, dbc._filename)
        dbc.session.add(
            database.PortalV2(
                guid='guid',
                label='label',
                first_seen=0,
                last_seen=0,
                latlng='123,45'
            )
        )
        dbc.session.commit()

        with self.assertLogs() as logs:
            # Set in the future
            dbc._connect_time += 10
            dbc.dispose()

        self.assertIn('skipping frag check', '\n'.join(logs.output))

    def test_frag_check_long_connection_no_changes(self):
        dbc = test_helper.database_connection(self)
        self.assertTrue(dbc.session)
        dbc._vacuum_reason = f'forced-{self.id()}'
        dbc.dispose()

        dbc = database.Database(dbc._directory, dbc._filename)
        dbc.session.commit()
        with self.assertLogs():
            # Set in the past
            dbc._connect_time -= 10
            dbc.dispose()

        # Just triggers code coverage

    def test_frag_check_long_connection_with_single_change(self):
        dbc = test_helper.database_connection(self)

        self.assertTrue(dbc.session)
        dbc._vacuum_reason = f'forced-{self.id()}'
        dbc.dispose()

        dbc = database.Database(dbc._directory, dbc._filename)
        dbc.session.add(
            database.PortalV2(
                guid='guid',
                label='label',
                first_seen=0,
                last_seen=0,
                latlng='123,45'
            )
        )
        dbc.session.commit()

        with self.assertLogs() as logs:
            # Set in the past
            dbc._connect_time -= 10
            dbc.dispose()

        logs_output = '\n'.join(logs.output)
        self.assertIn('total_changes:', logs_output)
        self.assertIn('fragmentation: 0.0', logs_output)

    def test_frag_check_long_connection_with_many_changes(self):
        dbc = test_helper.database_connection(self)

        self.assertTrue(dbc.session)
        dbc._vacuum_reason = f'forced-{self.id()}'
        dbc.dispose()

        dbc = database.Database(dbc._directory, dbc._filename)
        for lat in range(89):
            for lng in range(179):
                dbc.session.add(
                    database.PortalV2(
                        guid=f'guid-{lat:02}-{lng:03}',
                        label='label',
                        first_seen=0,
                        last_seen=0,
                        latlng=f'{lat},{lng}'
                    )
                )
        dbc.session.commit()

        with self.assertLogs() as logs:
            # Set in the past
            dbc._connect_time -= 10
            dbc.dispose()

        logs_output = '\n'.join(logs.output)
        self.assertIn('total_changes:', logs_output)
        self.assertIn('fragmentation: good time to vacuum', logs_output)

    def test_trigger_vacuum(self):
        dbc = test_helper.database_connection(self)
        for lng in range(45, 50):
            dbc.session.add(
                database.PortalV2(
                    guid=f'guid-{lng}',
                    label='label',
                    first_seen=0,
                    last_seen=0,
                    latlng=f'123,{lng}'
                )
            )
        dbc.session.commit()
        dbc.session.execute(database.sqlalchemy.delete(database.PortalV2))
        dbc.session.commit()

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout), self.assertLogs() as logs:
            dbc._vacuum_reason = 'testing-reason'
            dbc.dispose()

        self.assertIn('testing-reason', stdout.getvalue())
        self.assertIn('vacuuming: testing-reason', '\n'.join(logs.output))


if __name__ == '__main__':  # pragma: no cover
    unittest.main()
