"""Database connector for Ingress stuff."""

from __future__ import annotations

import logging
import pathlib
import typing

import geoalchemy2  # type: ignore[import]
import sqlalchemy
from sqlalchemy import orm

if typing.TYPE_CHECKING:  # pragma: no cover
    import argparse

    from mundane import app

# pylint: disable=too-few-public-methods


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


convention = {
    'ix': 'ix_%(column_0_label)s',
    'uq': 'uq_%(table_name)s_%(column_0_name)s',
    'ck': 'ck_%(table_name)s_%(constraint_name)s',
    'fk': 'fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s',
    'pk': 'pk_%(table_name)s',
}

metadata = sqlalchemy.schema.MetaData(naming_convention=convention)

Base = orm.declarative_base(metadata=metadata)  # pylint: disable=invalid-name


def latlng_to_point(latlng: str) -> geoalchemy2.elements.WKTElement:
    """Convert lat,lng to a geoalchemy wrapped POINT."""
    lat, lng = latlng.split(',')
    point = geoalchemy2.elements.WKTElement(f'POINT({lng} {lat})', srid=4326)
    return point


def latlng_dict_to_point(
        latlng: dict[str, str]) -> geoalchemy2.elements.WKTElement:
    """Convert lat,lng to a geoalchemy wrapped POINT."""
    point = geoalchemy2.elements.WKTElement(
        f'POINT({latlng["lng"]} {latlng["lat"]})', srid=4326)
    return point


def point_to_latlng(point: geoalchemy2.elements.WKTElement) -> str:
    """Convert a geoalchemy wrapped POINT to a lat,lng string."""
    shape = geoalchemy2.shape.to_shape(point)
    return f'{shape.y},{shape.x}'


class Portal(Base):  # pylint: disable=missing-docstring
    __tablename__ = 'portals'

    guid = sqlalchemy.Column(
        sqlalchemy.String, primary_key=True, nullable=False)
    label = sqlalchemy.Column(sqlalchemy.Unicode, nullable=False)
    first_seen = sqlalchemy.Column(
        sqlalchemy.Integer, nullable=False, index=True)
    last_seen = sqlalchemy.Column(
        sqlalchemy.Integer, nullable=False, index=True)
    latlng = sqlalchemy.Column(
        geoalchemy2.Geometry('POINT', srid=4326), nullable=False)

    def from_iitc(self, **kwargs):
        """Populate a row with an IITC bookmark style dict."""
        logging.debug('populating with: %s', kwargs)
        for key, value in list(kwargs.items()):
            if key == 'latlng':
                value = latlng_to_point(value)
            setattr(self, key, value)
        logging.debug('populated')
        return self

    def to_iitc(self):
        """Generate an IITC bookmark style dict."""
        portal = dict()

        for key in self.__mapper__.c.keys():
            portal[key] = getattr(self, key)
            if key == 'latlng':
                portal[key] = point_to_latlng(portal[key])

        return portal


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

    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True)  # pylint: disable=invalid-name
    latlng = sqlalchemy.Column(sqlalchemy.String, nullable=False, unique=True)
    address = sqlalchemy.Column(sqlalchemy.String, nullable=False)
    date = sqlalchemy.Column(sqlalchemy.Integer, nullable=False)


class Database:  # pylint: disable=missing-docstring

    def __init__(self, directory: str, filename: str):
        pathlib.Path(directory).mkdir(exist_ok=True)
        sql_logger = logging.getLogger('sqlalchemy')
        root_logger = logging.getLogger()
        sql_logger.setLevel(root_logger.getEffectiveLevel())
        engine = sqlalchemy.create_engine(
            f'sqlite:///{directory}/{filename}', future=True)
        self.session = orm.sessionmaker(bind=engine, future=True)()
        Base.metadata.create_all(engine)
