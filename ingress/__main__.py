"""Perform a number of Ingress related functions.

Mostly this works on data saved via IITC, like bookmarks and drawtools.

Note: This tool is currently being updated to use geometry/geographic
databases instead of python libraries for certain calculations.  Commands
marked with "(V)" have been verified to work under those conditions.
"""

import sys
import typing

from mundane import app
from mundane import log_mgr

from ingress import addresses
from ingress import bookmarks
from ingress import config
from ingress import database
from ingress import drawtools
from ingress import geo
from ingress import json
from ingress import portals
from ingress import routes


def main() -> typing.NoReturn:
    """The Ingress app."""
    log_mgr.set_root_log_level('INFO')
    ingress_app = app.ArgparseApp(
        use_log_mgr=True, use_docstring_for_description=sys.modules[__name__]
    )
    modules = (
        bookmarks, database, drawtools, geo, addresses, json, portals, routes,
        config
    )
    ingress_app.register_global_flags(modules)
    ingress_app.register_shared_flags(modules)
    ingress_app.register_commands(modules)

    sys.exit(ingress_app.run())


if __name__ == '__main__':  # pragma: no cover
    main()
