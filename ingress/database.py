"""Database connector for Ingress stuff."""

from __future__ import annotations

import dataclasses
import difflib
import logging
import pathlib
import typing
import uuid

import geoalchemy2  # type: ignore[import]
import sqlalchemy
from sqlalchemy import orm

if typing.TYPE_CHECKING:  # pragma: no cover
    import argparse

    from mundane import app

# pylint: disable=too-few-public-methods


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
        default=ctx.dirs.user_data_dir)

    ctx.global_flags.add_argument(
        '--db-name',
        help='Database file name (Default: %(default)s)',
        action='store',
        default=f'{ctx.appname}.db')

    ctx.register_after_parse_hook(init_db)


def init_db(args: argparse.Namespace):
    """Initialize the database using command line arguments."""

    # Do not bother if no command was given.
    if args.name:
        args.dbc = Database(args.db_dir, args.db_name)
        del args.db_dir
        del args.db_name


@sqlalchemy.event.listens_for(sqlalchemy.engine.Engine, 'connect')
def on_connect(dbapi_connection, _connection_record):
    """Defaults for our connection."""
    dbapi_connection.execute('PRAGMA foreign_keys=ON')
    dbapi_connection.enable_load_extension(True)
    dbapi_connection.load_extension('mod_spatialite')
    dbapi_connection.enable_load_extension(False)
    cur = dbapi_connection.execute('SELECT CheckSpatialMetaData();')
    if cur.fetchone()[0] < 1:
        dbapi_connection.execute('SELECT InitSpatialMetaData(1);')


@sqlalchemy.event.listens_for(sqlalchemy.engine.Engine, 'close')
def on_close(dbapi_connection, _connection_record):
    """Maintenance on close."""
    count = dbapi_connection.execute('PRAGMA freelist_count').fetchone()[0]
    if count > 10:
        print(f'Performing VACUUM as freelist {count=}')
        for row in dbapi_connection.execute('VACUUM'):
            print(row)


convention = {
    'ix': 'ix_%(column_0_label)s',
    'uq': 'uq_%(table_name)s_%(column_0_name)s',
    'ck': 'ck_%(table_name)s_%(constraint_name)s',
    'fk': 'fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s',
    'pk': 'pk_%(table_name)s',
}

metadata = sqlalchemy.schema.MetaData(naming_convention=convention)

Base = orm.declarative_base(metadata=metadata)  # pylint: disable=invalid-name


def latlng_dict_to_point(
        latlng: dict[str, str]) -> geoalchemy2.elements.WKTElement:
    """Convert lat,lng to a geoalchemy wrapped POINT."""
    point = geoalchemy2.elements.WKTElement(
        f'POINT({latlng["lng"]} {latlng["lat"]})', srid=4326)
    return point


def _latlng_to_point(latlng: str) -> geoalchemy2.elements.WKTElement:
    """Convert lat,lng to a geoalchemy wrapped POINT."""
    lat, lng = latlng.split(',')
    point = geoalchemy2.elements.WKTElement(f'POINT({lng} {lat})', srid=4326)
    return point


def _point_to_latlng(point: geoalchemy2.elements.WKTElement) -> str:
    """Convert a geoalchemy wrapped POINT to a lat,lng string."""
    shape = geoalchemy2.shape.to_shape(point)
    return f'{shape.y},{shape.x}'


class ReprMixin:
    """A reasonable default __repr__ implementation."""

    def __repr__(self):
        params = ', '.join(
            f'{key}={getattr(self, key)!r}'
            for key in self.__mapper__.c.keys())
        return f'{self.__class__.__name__}({params})'


class _Portal(Base):  # pylint: disable=missing-docstring
    __tablename__ = 'portals'

    guid = sqlalchemy.Column(
        sqlalchemy.String, primary_key=True, nullable=False)
    label = sqlalchemy.Column(sqlalchemy.Unicode, nullable=False)
    first_seen = sqlalchemy.Column(
        sqlalchemy.Integer, nullable=False, index=True)
    last_seen = sqlalchemy.Column(
        sqlalchemy.Integer, nullable=False, index=True)
    latlng = sqlalchemy.Column(geoalchemy2.Geometry('POINT', srid=4326))

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


class PortalV2(Base):  # pylint: disable=missing-docstring
    __tablename__ = 'v2_portals'

    guid = sqlalchemy.Column(
        sqlalchemy.String, primary_key=True, nullable=False)
    label = sqlalchemy.Column(sqlalchemy.Unicode, nullable=False)
    first_seen = sqlalchemy.Column(
        sqlalchemy.Integer, nullable=False, index=True)
    last_seen = sqlalchemy.Column(
        sqlalchemy.Integer, nullable=False, index=True)
    latlng = sqlalchemy.Column(sqlalchemy.String, nullable=False)
    lat = sqlalchemy.Column(
        sqlalchemy.String,
        sqlalchemy.Computed(
            'SUBSTR(latlng, 1, INSTR(latlng, ",") - 1)', persisted=False))
    lng = sqlalchemy.Column(
        sqlalchemy.String,
        sqlalchemy.Computed(
            'SUBSTR(latlng, INSTR(latlng, ",") + 1)', persisted=False))
    point = sqlalchemy.Column(
        geoalchemy2.Geometry('POINT', srid=4326),
        sqlalchemy.Computed(
            'ST_POINT(CAST(lng AS FLOAT), CAST(lat AS FLOAT))',
            persisted=True))

    def to_iitc(self) -> PortalDict:
        """Generate an IITC bookmark style dict."""
        portal = PortalDict()

        for key in self.__mapper__.c.keys():
            if key in PortalDict.__optional_keys__:  # pylint: disable=no-member
                portal[key] = getattr(  # type: ignore[literal-required]
                    self, key)

        return portal

    def __repr__(self):
        return (
            'PortalV2('
            f'label={self.label},'
            f' first_seen={self.first_seen},'
            f' last_seen={self.last_seen}'
            ')')


class ClusterLeader(Base):  # pylint: disable=missing-docstring
    __tablename__ = 'cluster_leaders'

    guid = sqlalchemy.Column(
        sqlalchemy.ForeignKey('portals.guid', ondelete='CASCADE'),
        primary_key=True)


class Leg(Base):  # pylint: disable=missing-docstring
    __tablename__ = 'legs'

    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True)  # pylint: disable=invalid-name
    begin_latlng = sqlalchemy.Column(sqlalchemy.String, nullable=False)
    end_latlng = sqlalchemy.Column(sqlalchemy.String, nullable=False)
    mode = sqlalchemy.Column(
        sqlalchemy.Enum('walking', 'driving'), nullable=False)
    date = sqlalchemy.Column(sqlalchemy.Integer, nullable=False)
    duration = sqlalchemy.Column(sqlalchemy.Integer, nullable=False)
    polyline = sqlalchemy.Column(sqlalchemy.Unicode, nullable=False)

    __table_args__ = (
        sqlalchemy.UniqueConstraint('begin_latlng', 'end_latlng', 'mode'),
    )  # yapf: disable


class Path(Base):  # pylint: disable=missing-docstring
    __tablename__ = 'paths'

    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True)  # pylint: disable=invalid-name
    begin_latlng = sqlalchemy.Column(sqlalchemy.String, nullable=False)
    end_latlng = sqlalchemy.Column(sqlalchemy.String, nullable=False)
    mode = sqlalchemy.Column(
        sqlalchemy.Enum('walking', 'driving'), nullable=False)
    date = sqlalchemy.Column(sqlalchemy.Integer, nullable=False)

    __table_args__ = (
        sqlalchemy.UniqueConstraint('begin_latlng', 'end_latlng', 'mode'),
    )  # yapf: disable


class PathLeg(Base):  # pylint: disable=missing-docstring
    __tablename__ = 'path_legs'

    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True)  # pylint: disable=invalid-name
    leg_id = sqlalchemy.Column(
        sqlalchemy.ForeignKey('legs.id', ondelete='CASCADE'))
    path_id = sqlalchemy.Column(
        sqlalchemy.ForeignKey('paths.id', ondelete='CASCADE'))


# If any path_leg is deleted, remove all associated ones
sqlalchemy.event.listen(
    PathLeg.__table__,  # pylint: disable=no-member
    'after_create',
    sqlalchemy.DDL(
        'CREATE TRIGGER delete_legs'
        ' AFTER DELETE ON path_legs'
        ' FOR EACH ROW'
        ' BEGIN'
        '  DELETE FROM path_legs'
        '  WHERE path_id == OLD.path_id;'
        ' END;'))


class Address(Base):  # pylint: disable=missing-docstring
    __tablename__ = 'addresses'

    latlng = sqlalchemy.Column(
        sqlalchemy.String, nullable=False, primary_key=True)
    lat = sqlalchemy.Column(
        sqlalchemy.String,
        sqlalchemy.Computed('SUBSTR(latlng, 1, INSTR(latlng, ",") - 1)'))
    lng = sqlalchemy.Column(
        sqlalchemy.String,
        sqlalchemy.Computed('SUBSTR(latlng, INSTR(latlng, ",") + 1)'))
    address = sqlalchemy.Column(sqlalchemy.String, nullable=False)
    date = sqlalchemy.Column(sqlalchemy.Integer, nullable=False)

    def __repr__(self):
        return (
            'Address('
            f'latlng={self.latlng!r},'
            f' address={self.address!r},'
            f' date={self.date!r}'
            ')')


class AddressType(Base):  # pylint: disable=missing-docstring
    __tablename__ = 'address_types'

    type = sqlalchemy.Column(
        sqlalchemy.String, nullable=False, primary_key=True)
    visibility = sqlalchemy.Column(
        sqlalchemy.Enum(
            'new', 'hide', 'show', create_constraint=True, name='visibility'),
        server_default='new',
        nullable=False)
    note = sqlalchemy.Column(sqlalchemy.String)

    def __repr__(self):
        return f'AddressType(type={self.type!r})'


class AddressTypeValue(Base):  # pylint: disable=missing-docstring
    __tablename__ = 'address_type_values'

    type = sqlalchemy.Column(
        sqlalchemy.ForeignKey('address_types.type', ondelete='CASCADE'),
        primary_key=True)
    value = sqlalchemy.Column(
        sqlalchemy.String, nullable=False, primary_key=True)
    pruning = sqlalchemy.Column(
        sqlalchemy.Enum(
            'unset',
            'remove',
            'ignore',
            create_constraint=True,
            name='pruning'),
        server_default='unset',
        nullable=False)
    note = sqlalchemy.Column(sqlalchemy.String)


class AddressTypeValueAssociation(Base):  # pylint: disable=missing-docstring
    __tablename__ = 'address_type_value_associations'

    latlng = sqlalchemy.Column(
        sqlalchemy.ForeignKey('addresses.latlng', ondelete='CASCADE'),
        primary_key=True)
    type = sqlalchemy.Column(
        sqlalchemy.String, nullable=False, primary_key=True)
    value = sqlalchemy.Column(
        sqlalchemy.String, nullable=False, primary_key=True)

    def __repr__(self):
        return (
            'AddressTypeValueAssociation('
            f'latlng={self.latlng!r},'
            f' type={self.type!r},'
            f' value={self.value!r}'
            ')')

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

    uuid = sqlalchemy.Column(
        sqlalchemy.String, nullable=False, primary_key=True)


class Place(UuidMixin, Base):  # pylint: disable=missing-docstring
    __tablename__ = 'places'

    label = sqlalchemy.Column(sqlalchemy.Unicode)
    latlng = sqlalchemy.Column(sqlalchemy.String, nullable=False, unique=True)
    lat = sqlalchemy.Column(
        sqlalchemy.String,
        sqlalchemy.Computed(
            'SUBSTR(latlng, 1, INSTR(latlng, ",") - 1)', persisted=False))
    lng = sqlalchemy.Column(
        sqlalchemy.String,
        sqlalchemy.Computed(
            'SUBSTR(latlng, INSTR(latlng, ",") + 1)', persisted=False))
    point = sqlalchemy.Column(
        geoalchemy2.Geometry('POINT', srid=4326),
        sqlalchemy.Computed(
            'ST_POINT(CAST(lng AS FLOAT), CAST(lat AS FLOAT))',
            persisted=True))
    note = sqlalchemy.Column(sqlalchemy.Unicode)


class BookmarkFolder(ReprMixin, UuidMixin, Base):  # pylint: disable=missing-docstring
    __tablename__ = 'bookmark_folders'

    label = sqlalchemy.Column(sqlalchemy.Unicode, nullable=False, unique=True)


class MapBookmark(Base):  # pylint: disable=missing-docstring
    __tablename__ = 'map_bookmarks'

    folder_id = sqlalchemy.Column(
        sqlalchemy.ForeignKey('bookmark_folders.uuid', ondelete='CASCADE'),
        nullable=False,
        primary_key=True)
    place_id = sqlalchemy.Column(
        sqlalchemy.ForeignKey('places.uuid', ondelete='CASCADE'),
        nullable=False,
        primary_key=True)
    zoom = sqlalchemy.Column(sqlalchemy.Integer)


class PortalBookmark(Base):  # pylint: disable=missing-docstring
    __tablename__ = 'portal_bookmarks'

    folder_uuid = sqlalchemy.Column(
        sqlalchemy.ForeignKey('bookmark_folders.uuid', ondelete='CASCADE'),
        nullable=False,
        primary_key=True)
    portal_uuid = sqlalchemy.Column(
        sqlalchemy.ForeignKey('v2_portals.guid', ondelete='CASCADE'),
        nullable=False,
        primary_key=True)


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
            ' (SUBSTR(latlng, 1, INSTR(latlng, ",") - 1)) VIRTUAL,'),
        (7, 'lng VARCHAR GENERATED ALWAYS AS () VIRTUAL,'),
        (
            7, 'lng VARCHAR GENERATED ALWAYS AS'
            ' (SUBSTR(latlng, INSTR(latlng, ",") + 1)) VIRTUAL,'),
        (
            8, 'point GEOMETRY GENERATED ALWAYS AS'
            ' (ST_POINT(CAST(lng AS FLOAT), CAST(lat AS FLOAT))) STORED,'),
        (
            8, 'point geometry(POINT,4326) GENERATED ALWAYS AS'
            ' (ST_POINT(CAST(lng AS FLOAT) STORED,'),
        (9, 'CONSTRAINT pk_v2_portals PRIMARY KEY (guid)'),
        (10, ')'),
    ))

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
            ' (SUBSTR(latlng, 1, INSTR(latlng, ",") - 1)) VIRTUAL,'),
        (5, 'lng VARCHAR GENERATED ALWAYS AS () VIRTUAL,'),
        (
            5, 'lng VARCHAR GENERATED ALWAYS AS'
            ' (SUBSTR(latlng, INSTR(latlng, ",") + 1)) VIRTUAL,'),
        (
            6, 'point geometry(POINT,4326) GENERATED ALWAYS AS'
            ' (ST_POINT(CAST(lng AS FLOAT) STORED,'),
        (
            6, 'point GEOMETRY GENERATED ALWAYS AS'
            ' (ST_POINT(CAST(lng AS FLOAT), CAST(lat AS FLOAT))) STORED,'),
        (7, 'note VARCHAR,'),
        (8, 'CONSTRAINT pk_places PRIMARY KEY (uuid),'),
        (9, 'CONSTRAINT uq_places_latlng UNIQUE (latlng)'),
        (10, ')'),
    ))

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
)


class Database:  # pylint: disable=missing-docstring

    def __init__(self, directory: str, filename: str):
        pathlib.Path(directory).mkdir(exist_ok=True)
        sql_logger = logging.getLogger('sqlalchemy')
        root_logger = logging.getLogger()
        sql_logger.setLevel(root_logger.getEffectiveLevel())
        self._engine = sqlalchemy.create_engine(
            f'sqlite:///{directory}/{filename}', future=True)
        self._sanity_check()
        self.session = orm.sessionmaker(bind=self._engine, future=True)()
        Base.metadata.create_all(self._engine)
        self._post_create_migrations()

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
                        bind=self._engine)).strip()
                dt_ddl = self._clean_ddl(raw_ddl)
                fallback_ddl = _FALLBACK_DDL.get(tablename, dict()).get(
                    raw_ddl, _DUMMY_DDL)
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
                                n=2)))
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
            for table in existing.tables.values():
                existing_tables[table.name] = ExistingTable(
                    ddls=self._clean_ddl(
                        str(sqlalchemy.schema.CreateTable(table))),
                    table=table)

            # https://github.com/sqlalchemy/sqlalchemy/discussions/11580
            if conn.dialect.driver == 'pysqlite':
                for row in conn.execute(sqlalchemy.text("""
                        SELECT name,sql
                        FROM sqlite_master
                        WHERE type = "table"
                        """)):
                    table = existing_tables.get(row.name)
                    if table:
                        table.ddls.update(self._clean_ddl(row.sql))

        return existing_tables

    def _clean_ddl(self, ddl: str) -> set[tuple[int, str]]:
        tuples = set(
            (number, line.strip())
            for number, line in enumerate(ddl.strip().splitlines()))
        return tuples

    def _post_create_migrations(self):
        # portals to v2_portals
        count = self.session.query(_Portal).count()
        if count:
            print('Performing a database migration.')
            print(
                f'Migrating {count} portals'
                f' from table "{_Portal.__tablename__}"'
                f' to table "{PortalV2.__tablename__}".')
            logging.info('migrating count: %d', count)
            portals = [
                portal.to_iitc() for portal in self.session.query(_Portal)
            ]
            logging.info('portal dictionaries generated: %d', len(portals))
            self.session.bulk_insert_mappings(PortalV2, portals)
            logging.info('bulk inserts completed')
            self.session.query(_Portal).delete()
            logging.info('bulk delete completed')
            self.session.commit()
            logging.info('finished migration')
            print('Migration complete.')
