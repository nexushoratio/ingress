#!/usr/bin/python -B
"""Perform a number of Ingress related functions."""

import argparse
import logging

import app
import attr

from ingress import bookmarks
from ingress import codes
from ingress import database
from ingress import drawtools
from ingress import geo
from ingress import json
from ingress import portals
from ingress import routes


@attr.s  # pylint: disable=missing-docstring,too-few-public-methods
class Context(object):
    argparse = attr.ib()
    shared_parsers = attr.ib()
    subparsers = attr.ib()


def main(app_parser):
    """Main."""
    parser = argparse.ArgumentParser(parents=[app_parser], description=__doc__)

    subparsers = parser.add_subparsers(
        title='commands', dest='name', help='subparser help')
    ctx = Context(
        argparse=argparse, shared_parsers=dict(), subparsers=subparsers)

    for module in (bookmarks, codes, drawtools, geo, json, portals, routes):
        register_shared_parsers = getattr(module, 'register_shared_parsers',
                                          None)
        if register_shared_parsers:
            register_shared_parsers(ctx)

    for module in (bookmarks, codes, drawtools, geo, json, portals, routes):
        register_module_parsers = getattr(module, 'register_module_parsers',
                                          None)
        if register_module_parsers:
            register_module_parsers(ctx)

    args = parser.parse_args()
    dbc = database.Database()
    logging.debug('Calling %s with %s', args.name, args)
    try:
        args.func(args, dbc)
    except AttributeError:
        parser.print_help()


app.run(main)
