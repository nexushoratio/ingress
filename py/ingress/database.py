"""Database connector for Ingress stuff."""

import sqlalchemy
from sqlalchemy.ext import declarative
from sqlalchemy import orm


@sqlalchemy.event.listens_for(sqlalchemy.engine.Engine, 'connect')
def set_sqlite_pragma(dbapi_connection, _connection_record):
    """Defaults for our connection."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


Base = declarative.declarative_base()  # pylint: disable=invalid-name


class Portal(Base):
    __tablename__ = 'portals'

    guid = sqlalchemy.Column(sqlalchemy.String, primary_key=True)
    label = sqlalchemy.Column(sqlalchemy.Unicode, nullable=False)
    first_seen = sqlalchemy.Column(
        sqlalchemy.Integer, nullable=False, index=True)
    last_seen = sqlalchemy.Column(
        sqlalchemy.Integer, nullable=False, index=True)
    code = sqlalchemy.Column(sqlalchemy.String)
    latlng = sqlalchemy.Column(sqlalchemy.String, nullable=False)


class Database(object):
    def __init__(self):
        engine = sqlalchemy.create_engine('sqlite:////home/nexus/ingress.db')
        self.session = orm.sessionmaker(bind=engine)()
        Base.metadata.create_all(engine)
