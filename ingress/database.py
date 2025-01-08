"""Database connector for Ingress stuff."""

from __future__ import annotations

import atexit
import collections
import dataclasses
import difflib
import functools
import logging
import pathlib
import time
import typing
import uuid

import geoalchemy2  # type: ignore[import]
import sqlalchemy
from sqlalchemy import orm
import wurlitzer  # type: ignore[import]

if typing.TYPE_CHECKING:  # pragma: no cover
    import argparse

    from mundane import app

WKB: typing.TypeAlias = geoalchemy2.WKBElement
WKT: typing.TypeAlias = geoalchemy2.WKTElement


@dataclasses.dataclass(kw_only=True)
class ExistingTable:
    """Information about existing tables for use with sanity checking."""
    ddls: set[tuple[int, str]]
    table: sqlalchemy.sql.schema.Table


class Error(Exception):
    """Base module exception."""


def mundane_global_flags(ctx: app.ArgparseApp):
    """Register global flags."""

    ctx.global_flags.add_argument(
        '--db-dir',
        help='Database directory (Default: %(default)s)',
        action='store',
        default=ctx.dirs.user_data_dir
    )

    ctx.global_flags.add_argument(
        '--db-name',
        help='Database file name (Default: %(default)s)',
        action='store',
        default=f'{ctx.appname}.db'
    )

    ctx.register_after_parse_hook(init_db)


def init_db(args: argparse.Namespace):
    """Initialize the database using command line arguments."""

    args.dbc = Database(args.db_dir, args.db_name)
    del args.db_dir
    del args.db_name


convention = {
    'ix': 'ix_%(column_0_label)s',
    'uq': 'uq_%(table_name)s_%(column_0_name)s',
    'ck': 'ck_%(table_name)s_%(constraint_name)s',
    'fk': 'fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s',
    'pk': 'pk_%(table_name)s',
}

metadata = sqlalchemy.schema.MetaData(naming_convention=convention)

Base = orm.declarative_base(metadata=metadata)


def latlng_dict_to_point(latlng: dict[str, str]) -> WKT:
    """Convert lat,lng to a geoalchemy wrapped POINT."""
    point = WKT(f'POINT({latlng["lng"]} {latlng["lat"]})', srid=4326)
    return point


def _latlng_to_point(latlng: str) -> WKT:
    """Convert lat,lng to a geoalchemy wrapped POINT."""
    lat, lng = latlng.split(',')
    point = WKT(f'POINT({lng} {lat})', srid=4326)
    return point


def _point_to_latlng(point: WKT) -> str:
    """Convert a geoalchemy wrapped POINT to a lat,lng string."""
    shape = geoalchemy2.shape.to_shape(point)
    return f'{shape.y},{shape.x}'


# pylint: disable=too-few-public-methods


class ReprMixin:
    """A reasonable default __repr__ implementation.

    Subclasses may specify a collection of columns to exclude from repr by
    overriding `_repr_exclude_keys`.
    """

    _repr_exclude_keys: tuple[str, ...] = ()

    def __repr__(self):
        params = ', '.join(
            f'{key}={getattr(self, key)!r}'
            for key in self.__mapper__.c.keys()
            if key not in self._repr_exclude_keys
        )
        return f'{self.__class__.__name__}({params})'


class _Portal(Base):  # pylint: disable=missing-class-docstring
    __tablename__ = 'portals'

    guid = sqlalchemy.Column(
        sqlalchemy.String, primary_key=True, nullable=False
    )
    label = sqlalchemy.Column(sqlalchemy.Unicode, nullable=False)
    first_seen = sqlalchemy.Column(
        sqlalchemy.Integer, nullable=False, index=True
    )
    last_seen = sqlalchemy.Column(
        sqlalchemy.Integer, nullable=False, index=True
    )
    latlng: geoalchemy2.WKBElement = sqlalchemy.Column(
        geoalchemy2.Geometry('POINT', srid=4326)
    )

    def to_iitc(self):
        """Generate an IITC bookmark style dict."""
        portal = dict()

        for key in self.__mapper__.c.keys():
            portal[key] = getattr(self, key)
            if key == 'latlng':
                portal[key] = _point_to_latlng(portal[key])

        return portal


class PortalDict(typing.TypedDict, total=False):
    """A dict equivalent for PortalV2.

    This is useful for processing JSON files.
    """
    guid: str
    label: str
    first_seen: int
    last_seen: int
    latlng: str


class PortalV2(ReprMixin, Base):  # pylint: disable=missing-class-docstring
    __tablename__ = 'v2_portals'

    _repr_exclude_keys = ('lat', 'lng', 'point')

    guid = sqlalchemy.Column(
        sqlalchemy.String, primary_key=True, nullable=False
    )
    label = sqlalchemy.Column(sqlalchemy.Unicode, nullable=False)
    first_seen = sqlalchemy.Column(
        sqlalchemy.Integer, nullable=False, index=True
    )
    last_seen = sqlalchemy.Column(
        sqlalchemy.Integer, nullable=False, index=True
    )
    latlng = sqlalchemy.Column(sqlalchemy.String, nullable=False)
    lat = sqlalchemy.Column(
        sqlalchemy.String,
        sqlalchemy.Computed(
            'SUBSTR(latlng, 1, INSTR(latlng, ",") - 1)', persisted=False
        )
    )
    lng = sqlalchemy.Column(
        sqlalchemy.String,
        sqlalchemy.Computed(
            'SUBSTR(latlng, INSTR(latlng, ",") + 1)', persisted=False
        )
    )
    point: geoalchemy2.WKBElement = sqlalchemy.Column(
        geoalchemy2.Geometry('POINT', srid=4326),
        sqlalchemy.Computed(
            'ST_POINT(CAST(lng AS FLOAT), CAST(lat AS FLOAT))',
            persisted=True
        )
    )

    def to_iitc(self) -> PortalDict:
        """Generate an IITC bookmark style dict."""
        portal = PortalDict()

        for key in self.__mapper__.c.keys():
            if key in PortalDict.__optional_keys__:  # pylint: disable=no-member
                portal[key  # type: ignore[literal-required]
                       ] = getattr(self, key)

        return portal


class ClusterLeader(Base):  # pylint: disable=missing-class-docstring
    __tablename__ = 'cluster_leaders'

    guid: str = sqlalchemy.Column(
        sqlalchemy.ForeignKey('portals.guid', ondelete='CASCADE'),
        primary_key=True
    )


class Leg(Base):  # pylint: disable=missing-class-docstring
    __tablename__ = 'legs'

    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True)
    begin_latlng = sqlalchemy.Column(sqlalchemy.String, nullable=False)
    end_latlng = sqlalchemy.Column(sqlalchemy.String, nullable=False)
    mode = sqlalchemy.Column(
        sqlalchemy.Enum('walking', 'driving'), nullable=False
    )
    date = sqlalchemy.Column(sqlalchemy.Integer, nullable=False)
    duration = sqlalchemy.Column(sqlalchemy.Integer, nullable=False)
    polyline = sqlalchemy.Column(sqlalchemy.Unicode, nullable=False)

    __table_args__ = (
        sqlalchemy.UniqueConstraint('begin_latlng', 'end_latlng', 'mode'),
    )  # yapf: disable


class Path(Base):  # pylint: disable=missing-class-docstring
    __tablename__ = 'paths'

    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True)
    begin_latlng = sqlalchemy.Column(sqlalchemy.String, nullable=False)
    end_latlng = sqlalchemy.Column(sqlalchemy.String, nullable=False)
    mode = sqlalchemy.Column(
        sqlalchemy.Enum('walking', 'driving'), nullable=False
    )
    date = sqlalchemy.Column(sqlalchemy.Integer, nullable=False)

    __table_args__ = (
        sqlalchemy.UniqueConstraint('begin_latlng', 'end_latlng', 'mode'),
    )  # yapf: disable


class PathLeg(Base):  # pylint: disable=missing-class-docstring
    __tablename__ = 'path_legs'

    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True)
    leg_id: str = sqlalchemy.Column(
        sqlalchemy.ForeignKey('legs.id', ondelete='CASCADE')
    )
    path_id: str = sqlalchemy.Column(
        sqlalchemy.ForeignKey('paths.id', ondelete='CASCADE')
    )


# If any path_leg is deleted, remove all associated ones
sqlalchemy.event.listen(
    PathLeg.__table__, 'after_create',
    sqlalchemy.DDL(
        'CREATE TRIGGER delete_legs'
        ' AFTER DELETE ON path_legs'
        ' FOR EACH ROW'
        ' BEGIN'
        '  DELETE FROM path_legs'
        '  WHERE path_id == OLD.path_id;'
        ' END;'
    )
)


class Address(ReprMixin, Base):  # pylint: disable=missing-class-docstring
    __tablename__ = 'addresses'

    _repr_exclude_keys = ('lat', 'lng')

    latlng = sqlalchemy.Column(
        sqlalchemy.String, nullable=False, primary_key=True
    )
    lat = sqlalchemy.Column(
        sqlalchemy.String,
        sqlalchemy.Computed('SUBSTR(latlng, 1, INSTR(latlng, ",") - 1)')
    )
    lng = sqlalchemy.Column(
        sqlalchemy.String,
        sqlalchemy.Computed('SUBSTR(latlng, INSTR(latlng, ",") + 1)')
    )
    address = sqlalchemy.Column(sqlalchemy.String, nullable=False)
    date = sqlalchemy.Column(sqlalchemy.Integer, nullable=False)


class AddressType(ReprMixin, Base):  # pylint: disable=missing-class-docstring
    __tablename__ = 'address_types'

    type = sqlalchemy.Column(
        sqlalchemy.String, nullable=False, primary_key=True
    )
    visibility = sqlalchemy.Column(
        sqlalchemy.Enum(
            'new', 'hide', 'show', create_constraint=True, name='visibility'
        ),
        server_default='new',
        nullable=False
    )
    note = sqlalchemy.Column(sqlalchemy.String)


class AddressTypeValue(ReprMixin, Base):  # pylint: disable=missing-class-docstring
    __tablename__ = 'address_type_values'

    type: str = sqlalchemy.Column(
        sqlalchemy.ForeignKey('address_types.type', ondelete='CASCADE'),
        primary_key=True
    )
    value = sqlalchemy.Column(
        sqlalchemy.String, nullable=False, primary_key=True
    )
    pruning = sqlalchemy.Column(
        sqlalchemy.Enum(
            'unset',
            'remove',
            'ignore',
            create_constraint=True,
            name='pruning'
        ),
        server_default='unset',
        nullable=False
    )
    note = sqlalchemy.Column(sqlalchemy.String)


class AddressTypeValueAssociation(ReprMixin, Base):  # pylint: disable=missing-class-docstring
    __tablename__ = 'address_type_value_associations'

    latlng: str = sqlalchemy.Column(
        sqlalchemy.ForeignKey('addresses.latlng', ondelete='CASCADE'),
        primary_key=True
    )
    type = sqlalchemy.Column(
        sqlalchemy.String, nullable=False, primary_key=True
    )
    value = sqlalchemy.Column(
        sqlalchemy.String, nullable=False, primary_key=True
    )

    __table_args__ = (
        sqlalchemy.ForeignKeyConstraint(
            ['type', 'value'],
            ['address_type_values.type', 'address_type_values.value'],
            ondelete='CASCADE'),
    )  # yapf: disable


class UuidMixin:
    """Automatically support UUID as a PK."""

    def __init__(self, **kwargs):
        if 'uuid' not in kwargs:
            kwargs['uuid'] = uuid.uuid4().hex
        super().__init__(**kwargs)

    uuid: str = sqlalchemy.Column(
        sqlalchemy.String, nullable=False, primary_key=True
    )


class Place(ReprMixin, UuidMixin, Base):  # pylint: disable=missing-class-docstring
    __tablename__ = 'places'

    _repr_exclude_keys = ('lat', 'lng', 'point')

    label = sqlalchemy.Column(sqlalchemy.Unicode)
    latlng = sqlalchemy.Column(sqlalchemy.String, nullable=False, unique=True)
    lat = sqlalchemy.Column(
        sqlalchemy.String,
        sqlalchemy.Computed(
            'SUBSTR(latlng, 1, INSTR(latlng, ",") - 1)', persisted=False
        )
    )
    lng = sqlalchemy.Column(
        sqlalchemy.String,
        sqlalchemy.Computed(
            'SUBSTR(latlng, INSTR(latlng, ",") + 1)', persisted=False
        )
    )
    point: geoalchemy2.WKBElement = sqlalchemy.Column(
        geoalchemy2.Geometry('POINT', srid=4326),
        sqlalchemy.Computed(
            'ST_POINT(CAST(lng AS FLOAT), CAST(lat AS FLOAT))',
            persisted=True
        )
    )
    note = sqlalchemy.Column(sqlalchemy.Unicode)


class BookmarkFolder(ReprMixin, UuidMixin, Base):  # pylint: disable=missing-class-docstring
    __tablename__ = 'bookmark_folders'

    label = sqlalchemy.Column(sqlalchemy.Unicode, nullable=False, unique=True)


class MapBookmark(ReprMixin, UuidMixin, Base):  # pylint: disable=missing-class-docstring
    __tablename__ = 'map_bookmarks'

    folder_id: str = sqlalchemy.Column(
        sqlalchemy.ForeignKey('bookmark_folders.uuid', ondelete='CASCADE'),
        nullable=False
    )
    place_id: str = sqlalchemy.Column(
        sqlalchemy.ForeignKey('places.uuid', ondelete='CASCADE'),
        nullable=False
    )
    zoom = sqlalchemy.Column(sqlalchemy.Integer, nullable=False)

    __table_args__ = (
        sqlalchemy.UniqueConstraint('folder_id', 'place_id'),
    )  # yapf: disable


class PortalBookmark(ReprMixin, UuidMixin, Base):  # pylint: disable=missing-class-docstring
    __tablename__ = 'portal_bookmarks'

    folder_id: str = sqlalchemy.Column(
        sqlalchemy.ForeignKey('bookmark_folders.uuid', ondelete='CASCADE'),
        nullable=False
    )
    portal_id: str = sqlalchemy.Column(
        sqlalchemy.ForeignKey('v2_portals.guid', ondelete='CASCADE'),
        nullable=False
    )

    __table_args__ = (
        sqlalchemy.UniqueConstraint('folder_id', 'portal_id'),
    )  # yapf: disable

# The .strip() at the end is important
_KNOWN_PORTALS_V2 = """
CREATE TABLE v2_portals (
	guid VARCHAR NOT NULL, 
	label VARCHAR NOT NULL, 
	first_seen INTEGER NOT NULL, 
	last_seen INTEGER NOT NULL, 
	latlng VARCHAR NOT NULL, 
	lat VARCHAR GENERATED ALWAYS AS (SUBSTR(latlng, 1, INSTR(latlng, ",") - 1)) VIRTUAL, 
	lng VARCHAR GENERATED ALWAYS AS (SUBSTR(latlng, INSTR(latlng, ",") + 1)) VIRTUAL, 
	point geometry(POINT,4326) GENERATED ALWAYS AS (ST_POINT(CAST(lng AS FLOAT), CAST(lat AS FLOAT))) STORED, 
	CONSTRAINT pk_v2_portals PRIMARY KEY (guid)
)
""".strip()

_ACCEPTABLE_PORTALS_V2 = set(
    (
        (0, 'CREATE TABLE v2_portals ('),
        (1, 'guid VARCHAR NOT NULL,'),
        (2, 'label VARCHAR NOT NULL,'),
        (3, 'first_seen INTEGER NOT NULL,'),
        (4, 'last_seen INTEGER NOT NULL,'),
        (5, 'latlng VARCHAR NOT NULL,'),
        (6, 'lat VARCHAR GENERATED ALWAYS AS () VIRTUAL,'),
        (
            6, 'lat VARCHAR GENERATED ALWAYS AS'
            ' (SUBSTR(latlng, 1, INSTR(latlng, ",") - 1)) VIRTUAL,'
        ),
        (7, 'lng VARCHAR GENERATED ALWAYS AS () VIRTUAL,'),
        (
            7, 'lng VARCHAR GENERATED ALWAYS AS'
            ' (SUBSTR(latlng, INSTR(latlng, ",") + 1)) VIRTUAL,'
        ),
        (
            8, 'point GEOMETRY GENERATED ALWAYS AS'
            ' (ST_POINT(CAST(lng AS FLOAT), CAST(lat AS FLOAT))) STORED,'
        ),
        (
            8, 'point geometry(POINT,4326) GENERATED ALWAYS AS'
            ' (ST_POINT(CAST(lng AS FLOAT) STORED,'
        ),
        (9, 'CONSTRAINT pk_v2_portals PRIMARY KEY (guid)'),
        (10, ')'),
    )
)

_KNOWN_PLACES = """
CREATE TABLE places (
	uuid VARCHAR NOT NULL, 
	label VARCHAR, 
	latlng VARCHAR NOT NULL, 
	lat VARCHAR GENERATED ALWAYS AS (SUBSTR(latlng, 1, INSTR(latlng, ",") - 1)) VIRTUAL, 
	lng VARCHAR GENERATED ALWAYS AS (SUBSTR(latlng, INSTR(latlng, ",") + 1)) VIRTUAL, 
	point geometry(POINT,4326) GENERATED ALWAYS AS (ST_POINT(CAST(lng AS FLOAT), CAST(lat AS FLOAT))) STORED, 
	note VARCHAR, 
	CONSTRAINT pk_places PRIMARY KEY (uuid), 
	CONSTRAINT uq_places_latlng UNIQUE (latlng)
)
""".strip()

_ACCEPTABLE_PLACES = set(
    (
        (0, 'CREATE TABLE places ('),
        (1, 'uuid VARCHAR NOT NULL,'),
        (2, 'label VARCHAR,'),
        (3, 'latlng VARCHAR NOT NULL,'),
        (4, 'lat VARCHAR GENERATED ALWAYS AS () VIRTUAL,'),
        (
            4, 'lat VARCHAR GENERATED ALWAYS AS'
            ' (SUBSTR(latlng, 1, INSTR(latlng, ",") - 1)) VIRTUAL,'
        ),
        (5, 'lng VARCHAR GENERATED ALWAYS AS () VIRTUAL,'),
        (
            5, 'lng VARCHAR GENERATED ALWAYS AS'
            ' (SUBSTR(latlng, INSTR(latlng, ",") + 1)) VIRTUAL,'
        ),
        (
            6, 'point geometry(POINT,4326) GENERATED ALWAYS AS'
            ' (ST_POINT(CAST(lng AS FLOAT) STORED,'
        ),
        (
            6, 'point GEOMETRY GENERATED ALWAYS AS'
            ' (ST_POINT(CAST(lng AS FLOAT), CAST(lat AS FLOAT))) STORED,'
        ),
        (7, 'note VARCHAR,'),
        (8, 'CONSTRAINT pk_places PRIMARY KEY (uuid),'),
        (9, 'CONSTRAINT uq_places_latlng UNIQUE (latlng)'),
        (10, ')'),
    )
)

# Work around bugs in sqlite reflection
# https://github.com/sqlalchemy/sqlalchemy/issues/11582
# 'tablename': {'create_table_output': hand_rolled_clean_ddl}
_FALLBACK_DDL: dict[str, dict[str, set[tuple[int, str]]]] = {
    'v2_portals': {
        _KNOWN_PORTALS_V2: _ACCEPTABLE_PORTALS_V2,
    },
    'places': {
        _KNOWN_PLACES: _ACCEPTABLE_PLACES,
    },
}

_DUMMY_DDL = frozenset((-1, ''),)

_AUTO_DROPS = (
    'cluster_leaders',
    'legs',
    'path_legs',
    'paths',
    'places',
    'bookmark_folders',
    'map_bookmarks',
    'portal_bookmarks',
)


class Database:  # pylint: disable=missing-class-docstring

    _engine: sqlalchemy.engine.Engine
    _session: sqlalchemy.orm.Session

    def __init__(
        self,
        directory: str,
        filename: str,
    ):
        logging.info('init: %s, %s', directory, filename)
        self._directory = directory
        self._filename = filename
        self._connect_time = 0.0
        self._spatialite_initialized = False
        self._vacuum_reason = None
        sql_logger = logging.getLogger('sqlalchemy')
        root_logger = logging.getLogger()
        sql_logger.setLevel(root_logger.getEffectiveLevel())

    @functools.cached_property
    def session(self) -> sqlalchemy.orm.Session:
        """Create and return the session."""
        pathlib.Path(self._directory).mkdir(exist_ok=True)
        self._engine = sqlalchemy.create_engine(
            f'sqlite:///{self._directory}/{self._filename}',
            future=True,
            poolclass=sqlalchemy.pool.StaticPool
        )
        sqlalchemy.event.listen(
            self._engine, 'connect', self._connect, named=True
        )
        sqlalchemy.event.listen(
            self._engine, 'close', self._close, named=True
        )
        self._sanity_check()
        self._session = orm.sessionmaker(bind=self._engine, future=True)()

        if self._spatialite_initialized:
            logging.info(
                'Ignore the following error messages about'
                ' updateTableTriggers()'
            )
            logging.info('For details see:')
            logging.info(
                'https://github.com/geoalchemy/geoalchemy2/issues/519'
            )
        with wurlitzer.pipes() as (stdout, stderr):
            Base.metadata.create_all(self._engine)

        for line in stdout.read().splitlines():
            logging.info('create_all stdout: %s', line)  # pragma: no cover
        for line in stderr.read().splitlines():
            logging.info('create_all stderr: %s', line)

        self._post_create_migrations()
        atexit.register(self.dispose)
        return self._session

    def dispose(self):
        """Orderly cleanup."""
        atexit.unregister(self.dispose)
        if hasattr(self, '_engine') and self._engine:
            self._engine.dispose()

    def __repr__(self):
        params = ', '.join(
            (
                f'directory={self._directory}',
                f'filename={self._filename}',
            )
        )

        return f'{self.__class__.__name__}({params})'

    def _connect(self, **kwargs):
        """Set defaults for our connection."""
        conn = kwargs['dbapi_connection']
        self._connect_time = time.time()
        conn.execute('PRAGMA foreign_keys=ON')
        conn.enable_load_extension(True)
        conn.load_extension('mod_spatialite')
        conn.enable_load_extension(False)
        if conn.execute('SELECT CheckSpatialMetaData()').fetchone()[0] < 1:
            conn.execute('SELECT InitSpatialMetaData(1)')
            self._spatialite_initialized = True

    def _close(self, **kwargs):
        """Maintenance on close."""
        conn = kwargs['dbapi_connection']
        conn.execute('PRAGMA optimize')
        count = conn.execute('PRAGMA freelist_count').fetchone()[0]
        logging.info('freelist_count: %d', count)
        self._frag_check(conn)
        if self._vacuum_reason:
            logging.info('vacuuming')
            print(f'Performing VACUUM because:\n  {self._vacuum_reason}')
            for row in conn.execute('VACUUM'):
                print(row)

    def _frag_check(self, conn):
        """Compute possible sqlite fragmentation."""
        if conn.total_changes:
            logging.info('total_changes: %d', conn.total_changes)
            time_connected = time.time() - self._connect_time
            logging.info('time connected: %f', time_connected)
            # Using dbstat takes time (probably linear based upon number of
            # pages), so only check when lots of work was done.
            if time_connected > 1.0:
                prev = 0
                gaps = collections.Counter()
                pages = collections.Counter()
                for row in conn.execute('SELECT name, pageno'
                                        ' FROM dbstat'
                                        ' ORDER BY name, pageno'):
                    name, pageno = row
                    pages[name] += 1
                    if (pageno - prev) > 1:
                        gaps[name] += 1
                    prev = pageno
                sum_gaps = 0
                sum_pages = 0
                for name, cnt in gaps.most_common():
                    sum_pages += pages[name]
                    # Only look at names with some number of gaps.
                    if cnt > 10:
                        sum_gaps += cnt
                if sum_pages:
                    fragged = 1.0 * sum_gaps / sum_pages
                    logging.info('fragmentation: %f', fragged)
                    # 10% fragmentation seems like a good starting point
                    if fragged > 0.1:
                        logging.info('fragmentation: good time to vacuum')
                else:
                    logging.info('no measurable fragmentation')
            else:
                logging.info(
                    'Time connected was too short, skipping frag check.'
                )

    def _sanity_check(self):
        """This is a proxy for doing proper migrations."""
        no_drop = list()
        to_drop = list()
        existing_tables = self._load_existing_tables()
        for defined_table in reversed(Base.metadata.sorted_tables):
            tablename = defined_table.name
            table = existing_tables.get(tablename)
            if table:
                raw_ddl = str(
                    sqlalchemy.schema.CreateTable(defined_table).compile(
                        bind=self._engine
                    )
                ).strip()
                dt_ddl = self._clean_ddl(raw_ddl)
                fallback_ddl = _FALLBACK_DDL.get(tablename, dict()
                                                 ).get(raw_ddl, _DUMMY_DDL)
                if not (dt_ddl.issubset(table.ddls)
                        or fallback_ddl.issubset(table.ddls)):
                    dt_sql = [f'{x}\n' for x in sorted(dt_ddl)]
                    et_sql = [f'{x}\n' for x in sorted(table.ddls)]
                    diffs = ''.join(
                        list(
                            difflib.unified_diff(
                                et_sql,
                                dt_sql,
                                fromfile='existing',
                                tofile='defined',
                                n=2
                            )
                        )
                    )
                    if tablename in _AUTO_DROPS:
                        to_drop.append((tablename, diffs))
                    else:
                        logging.debug('raw_ddl:\n%s', raw_ddl)
                        logging.debug('et_sql:\n%s', ''.join(et_sql))
                        no_drop.append((tablename, diffs))

        if no_drop:
            msg = ['Unhandled tables with differences:']
            for tablename, diffs in no_drop:
                msg.append(f'  {tablename}:\n{diffs}')
            msg.append('')
            raise Error('\n'.join(msg))

        for tablename, diffs in to_drop:
            print(f'dropping: {tablename}\n{diffs}')
            table = existing_tables.get(tablename)
            if table:
                table.table.drop(bind=self._engine)

    def _load_existing_tables(self) -> dict[str, ExistingTable]:
        """Get information about existing tables."""
        existing_tables = dict()
        with self._engine.connect() as conn:
            existing = sqlalchemy.schema.MetaData()
            existing.reflect(bind=conn)
            for value in existing.tables.values():
                existing_tables[value.name] = ExistingTable(
                    ddls=self._clean_ddl(
                        str(sqlalchemy.schema.CreateTable(value))
                    ),
                    table=value
                )

            # https://github.com/sqlalchemy/sqlalchemy/discussions/11580
            if conn.dialect.driver == 'pysqlite':
                for row in conn.execute(sqlalchemy.text("""
                        SELECT name,sql
                        FROM sqlite_master
                        WHERE type = "table"
                        """)):
                    existing_table = existing_tables.get(row.name)
                    if existing_table:
                        existing_table.ddls.update(self._clean_ddl(row.sql))

        return existing_tables

    def _clean_ddl(self, ddl: str) -> set[tuple[int, str]]:
        """Generate normalized DDL for easier comparison."""
        tuples = set(
            (number, line.strip())
            for number, line in enumerate(ddl.strip().splitlines())
        )
        return tuples

    def _post_create_migrations(self):
        """Migrate portals to v2_portals."""
        stmt = sqlalchemy.select(sqlalchemy.func.count()).select_from(_Portal)
        count = self._session.scalar(stmt)
        if count:
            print('Performing a database migration.')
            print(
                f'Migrating {count} portals'
                f' from table "{_Portal.__tablename__}"'
                f' to table "{PortalV2.__tablename__}".'
            )
            logging.info('migrating count: %d', count)
            stmt = sqlalchemy.select(_Portal)
            portals = [
                row._Portal.to_iitc() for row in self._session.execute(stmt)  # pylint: disable=protected-access
            ]
            logging.info('portal dictionaries generated: %d', len(portals))
            self._session.bulk_insert_mappings(PortalV2, portals)
            logging.info('bulk inserts completed')
            stmt = sqlalchemy.delete(_Portal)
            self._session.execute(stmt)
            logging.info('bulk delete completed')
            self._session.commit()
            logging.info('finished migration')
            print('Migration complete.')
