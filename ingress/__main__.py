"""Perform a number of Ingress related functions."""

import sys

from mundane import app

from ingress import bookmarks
from ingress import database
from ingress import drawtools
from ingress import geo
from ingress import json
from ingress import portals
from ingress import routes


def main():
    """The Ingress app."""
    ingress_app = app.ArgparseApp(use_log_mgr=True)
    modules = (bookmarks, drawtools, geo, json, portals, routes)
    ingress_app.register_global_flags(modules)
    ingress_app.register_shared_flags(modules)
    ingress_app.register_commands(modules)

    dbc = database.Database()
    ingress_app.parser.set_defaults(dbc=dbc)

    sys.exit(ingress_app.run())

if __name__ == '__main__':
    main()
