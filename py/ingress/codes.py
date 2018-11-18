"""Functions to manage and use location codes associated with portals."""

from ingress import database

_BINARY = {
    'true': True,
    'True': True,
    'false': False,
    'False': False,
}

_TRINARY = {
    'true': True,
    'True': True,
    'false': False,
    'False': False,
    'null': 'null',
}


def register_module_parsers(ctx):
    """Parser registration API."""
    code_write_parser = ctx.argparse.ArgumentParser(add_help=False)
    code_write_parser.add_argument(
        '-c',
        '--code',
        action='store',
        type=unicode,
        required=True,
        help='The location code.')

    code_read_parser = ctx.argparse.ArgumentParser(add_help=False)
    code_read_parser.add_argument(
        '-c',
        '--code',
        action='store',
        type=unicode,
        help='The location code.')

    label_parser = ctx.argparse.ArgumentParser(add_help=False)
    label_parser.add_argument(
        '-l',
        '--label',
        action='store',
        type=unicode,
        help='Label for the location code.')

    keep_write_parser = ctx.argparse.ArgumentParser(add_help=False)
    keep_write_parser.add_argument(
        '-k',
        '--keep',
        type=lambda x: _BINARY.get(x, x),
        choices=(True, False),
        help=('Controls whether or not to keep portals with this location code'
              ' during the prune operations.'))

    keep_read_parser = ctx.argparse.ArgumentParser(add_help=False)
    keep_read_parser.add_argument(
        '-k',
        '--keep',
        type=lambda x: _TRINARY.get(x, x),
        choices=(True, False, 'null'),
        help=('Controls whether or not to keep portals with this location code'
              ' during the prune operations.'))

    parser = ctx.subparsers.add_parser(
        'codes-set',
        parents=[code_write_parser, label_parser, keep_write_parser],
        description=setter.__doc__,
        help=setter.__doc__)
    parser.set_defaults(func=setter)

    parser = ctx.subparsers.add_parser(
        'codes-get',
        parents=[code_read_parser, label_parser, keep_read_parser],
        description=getter.__doc__,
        help=getter.__doc__)
    parser.set_defaults(func=getter)

    parser = ctx.subparsers.add_parser(
        'codes-delete',
        parents=[code_write_parser],
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
    query = dbc.session.query(database.Code)
    if args.code is not None:
        query = query.filter(database.Code.code == args.code)
    if args.label is not None:
        query = query.filter(database.Code.label == args.label)
    if args.keep is not None:
        keep = args.keep
        if keep == 'null':
            keep = None
        query = query.filter(database.Code.keep == keep)
    for db_code in query:
        print '%(code)8s | %(keep)4s | %(label)s' % {
            'code': db_code.code,
            'keep': db_code.keep,
            'label': db_code.label,
        }


def deleter(args, dbc):
    """Delete a location code."""
    code = dbc.session.query(database.Code).get(args.code)
    if code is not None:
        print 'deleting...'
        dbc.session.delete(code)
        dbc.session.commit()


def pruner(args, dbc):
    """Prune portals based upon keep status of location codes."""
    pass
