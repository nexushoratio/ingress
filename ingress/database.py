"""Database connector for Ingress stuff."""

from __future__ import annotations

import logging
import pathlib
import typing

import sqlalchemy
from sqlalchemy.ext import declarative
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
    dbapi_connection.enable_load_extension(True)
    dbapi_connection.load_extension('mod_spatialite')
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


Base = declarative.declarative_base()  # pylint: disable=invalid-name


class Portal(Base):  # pylint: disable=missing-docstring
    __tablename__ = 'portals'

    guid = sqlalchemy.Column(
        sqlalchemy.String, primary_key=True, nullable=False)
    label = sqlalchemy.Column(sqlalchemy.Unicode, nullable=False)
    first_seen = sqlalchemy.Column(
        sqlalchemy.Integer, nullable=False, index=True)
    last_seen = sqlalchemy.Column(
        sqlalchemy.Integer, nullable=False, index=True)
    latlng = sqlalchemy.Column(sqlalchemy.String, nullable=False)

    def update(self, **kwargs):
        """Update a row using kwargs just like the initial creation did."""
        logging.debug('updating with: %s', kwargs)
        for key, value in list(kwargs.items()):
            setattr(self, key, value)
        logging.debug('updated')


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
        engine = sqlalchemy.create_engine(f'sqlite:///{directory}/{filename}')
        self.session = orm.sessionmaker(bind=engine)()
        Base.metadata.create_all(engine)
