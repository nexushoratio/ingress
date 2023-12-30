"""Functions to manage and use location codes associated with portals."""

from ingress import database

_BINARY = {
    'true': True,
    'True': True,
    'y': True,
    'Y': True,
    'false': False,
    'False': False,
    'n': False,
    'N': False,
}

_TRINARY = _BINARY.copy()
_TRINARY.update({'null': 'null'})


def register_module_parsers(ctx):
    """Parser registration API."""
    code_write_parser = ctx.argparse.ArgumentParser(add_help=False)
    code_write_parser.add_argument(
        '-c',
        '--code',
        action='store',
        type=str,
        required=True,
        help='The location code.')

    code_read_parser = ctx.argparse.ArgumentParser(add_help=False)
    code_read_parser.add_argument(
        '-c', '--code', action='store', type=str, help='The location code.')

    label_parser = ctx.argparse.ArgumentParser(add_help=False)
    label_parser.add_argument(
        '-l',
        '--label',
        action='store',
        type=str,
        help='Label for the location code.')

    keep_write_parser = ctx.argparse.ArgumentParser(add_help=False)
    keep_write_parser.add_argument(
        '-k',
        '--keep',
        type=lambda x: _BINARY.get(x, x),
        choices=(True, False),
        help=(
            'Controls whether or not to keep portals with this location code'
            ' during the prune operations.'))

    keep_read_parser = ctx.argparse.ArgumentParser(add_help=False)
    keep_read_parser.add_argument(
        '-k',
        '--keep',
        type=lambda x: _TRINARY.get(x, x),
        choices=(True, False, 'null'),
        help=(
            'Controls whether or not to keep portals with this location code'
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
    parser.add_argument(
        '-m',
        '--mode',
        choices=('new-codes-only', 'dry-run', 'full-pruning'),
        default='new-codes-only',
        help=(
            'Scan for new codes only, a pretend run, or a full commitment'
            ' to pruning.'))
    parser.set_defaults(func=pruner)


def setter(args):
    """Sets a location code, creating it if necessary."""
    dbc = args.dbc
    db_code = dbc.session.query(database.Code).get(args.code)
    if db_code is None:
        db_code = database.Code(code=args.code)
    if args.keep is not None:
        db_code.keep = args.keep
    if args.label is not None:
        db_code.label = args.label
    dbc.session.add(db_code)
    dbc.session.commit()


def getter(args):
    """Display one or more location codes."""
    dbc = args.dbc
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
        print(
            (
                '%(code)8s | %(keep)4s | %(label)s' % {
                    'code': db_code.code,
                    'keep': db_code.keep,
                    'label': db_code.label,
                }))


def deleter(args):
    """Delete a location code."""
    dbc = args.dbc
    code = dbc.session.query(database.Code).get(args.code)
    if code is not None:
        print('deleting...')
        dbc.session.delete(code)
        dbc.session.commit()


def pruner(args):
    """Prune portals based upon keep status of location codes."""
    dbc = args.dbc
    all_codes = set()
    delete_codes = set()
    # Probably better done as a join
    for db_code in dbc.session.query(database.Code):
        all_codes.add(db_code.code)
        if db_code.keep is False:
            delete_codes.add(db_code.code)

    for db_portal in dbc.session.query(database.Portal):
        code = db_portal.code
        if code not in all_codes:
            print(('New code: %s' % code))
            dbc.session.add(database.Code(code=code))
            all_codes.add(code)
        if args.mode != 'new-codes-only':
            if code in delete_codes:
                print(('Pruning %s - %s' % (db_portal.guid, db_portal.label)))
                dbc.session.delete(db_portal)

    if args.mode == 'dry-run':
        dbc.session.rollback()
    else:
        dbc.session.commit()
