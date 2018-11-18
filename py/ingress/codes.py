"""Functions to manage and use location codes associated with portals."""

from ingress import database

_BOOLY = {
    'true': True,
    'True': True,
    'false': False,
    'False': False,
}


def register_module_parsers(ctx):
    """Parser registration API."""
    code_parser = ctx.argparse.ArgumentParser(add_help=False)
    code_parser.add_argument(
        '-c',
        '--code',
        action='store',
        type=unicode,
        required=True,
        help='The location code.')
    code_parser.add_argument(
        '-l',
        '--label',
        action='store',
        type=unicode,
        help='Label for the location code.')
    code_parser.add_argument(
        '-k',
        '--keep',
        type=lambda x: _BOOLY.get(x, x),
        choices=(True, False),
        help=('Controls whether or not to keep portals with this location code'
              ' during the prune operations.'))
    parser = ctx.subparsers.add_parser(
        'codes-set',
        parents=[code_parser],
        description=setter.__doc__,
        help=setter.__doc__)
    parser.set_defaults(func=setter)

    parser = ctx.subparsers.add_parser(
        'codes-get',
        parents=[code_parser],
        description=getter.__doc__,
        help=getter.__doc__)
    parser.set_defaults(func=getter)

    parser = ctx.subparsers.add_parser(
        'codes-delete',
        parents=[code_parser],
        description=deleter.__doc__,
        help=deleter.__doc__)
    parser.set_defaults(func=deleter)

    parser = ctx.subparsers.add_parser(
        'codes-prune', description=pruner.__doc__, help=pruner.__doc__)
    parser.set_defaults(func=pruner)


def setter(args, dbc):
    """Sets a location code, creating it if necessary."""
    db_code = dbc.session.query(database.Code).get(args.code)
    if db_code is None:
        db_code = database.Code(code=args.code)
    if args.keep is not None:
        db_code.keep = args.keep
    if args.label is not None:
        db_code.label = args.label
    dbc.session.add(db_code)
    dbc.session.commit()


def getter(args, dbc):
    """Display one or more location codes."""
    pass


def deleter(args, dbc):
    """Delete a location code."""
    pass


def pruner(args, dbc):
    """Prune portals based upon keep status of location codes."""
    pass
