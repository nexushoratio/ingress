"""Database connector for Ingress stuff."""

import logging
import sqlalchemy
from sqlalchemy.ext import declarative
from sqlalchemy import orm

# pylint: disable=too-few-public-methods


@sqlalchemy.event.listens_for(sqlalchemy.engine.Engine, 'connect')
def set_sqlite_pragma(dbapi_connection, _connection_record):
    """Defaults for our connection."""
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
    code = sqlalchemy.Column(sqlalchemy.String)
    latlng = sqlalchemy.Column(sqlalchemy.String, nullable=False)

    def update(self, **kwargs):
        """Update a row using kwargs just like the initial creation did."""
        logging.debug('updating with: %s', kwargs)
        for key, value in kwargs.iteritems():
            setattr(self, key, value)
        logging.debug('updated')


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


class PathLegs(Base):  # pylint: disable=missing-docstring
    __tablename__ = 'path_legs'

    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True)  # pylint: disable=invalid-name
    leg_id = sqlalchemy.Column(
        sqlalchemy.ForeignKey(
            'legs.id', ondelete='CASCADE'))
    path_id = sqlalchemy.Column(
        sqlalchemy.ForeignKey(
            'paths.id', ondelete='CASCADE'))


sqlalchemy.event.listen(
    PathLegs.__table__,  # pylint: disable=no-member
    'after_create',
    sqlalchemy.DDL('CREATE TRIGGER delete_legs'
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


class Database(object):
    def __init__(self):

        sql_logger = logging.getLogger('sqlalchemy')
        root_logger = logging.getLogger()
        sql_logger.setLevel(root_logger.getEffectiveLevel())
        engine = sqlalchemy.create_engine('sqlite:////home/nexus/ingress.db')
        self.session = orm.sessionmaker(bind=engine)()
        Base.metadata.create_all(engine)
