"""Functions to manage and use location codes associated with portals."""


def register_module_parsers(ctx):
    """Parser registration API."""
    parser = ctx.subparsers.add_parser(
        'codes-create', description=create.__doc__, help=create.__doc__)
    parser.set_defaults(func=create)

    parser = ctx.subparsers.add_parser(
        'codes-read', description=read.__doc__, help=read.__doc__)
    parser.set_defaults(func=read)

    parser = ctx.subparsers.add_parser(
        'codes-update', description=update.__doc__, help=update.__doc__)
    parser.set_defaults(func=update)

    parser = ctx.subparsers.add_parser(
        'codes-delete', description=delete.__doc__, help=delete.__doc__)
    parser.set_defaults(func=read)

    parser = ctx.subparsers.add_parser(
        'codes-prune', description=prune.__doc__, help=prune.__doc__)
    parser.set_defaults(func=read)


def create(args, dbc):
    """Create a new location code."""
    pass


def read(args, dbc):
    """Display location codes."""
    pass


def update(args, dbc):
    """Update an existing location code."""
    pass


def delete(args, dbc):
    """Delete a location code."""
    pass


def prune(args, dbc):
    """Prune portals based upon keep status of location codes."""
    pass
