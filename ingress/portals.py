"""Functions to work with portals directly."""

from __future__ import annotations

import collections
import operator
import typing

from ingress import bookmarks
from ingress import database

if typing.TYPE_CHECKING:  # pragma: no cover
    import argparse

    from mundane import app

Statement: typing.TypeAlias = database.sqlalchemy.sql.selectable.Select
ValidFields: typing.TypeAlias = tuple[str, ...]


class Error(Exception):
    """Base module exception."""


SHOW_FORMAT = '{label}\nhttps://www.ingress.com/intel?pll={latlng}'


def mundane_commands(ctx: app.ArgparseApp):
    """Register commands."""

    class QueryBuilder(ctx.argparse_api.Action):  # type: ignore[name-defined] # pylint: disable=too-few-public-methods
        """Callback action to accumulate flags by type, in order."""
        FILTERS = ('gt', 'ge', 'in', 'not_in', 'lt', 'le')
        ORDERINGS = ('asc', 'desc')
        NUMERIC = ('limit',)
        GROUPINGS = ('group_by',)

        def __init__(self, *args, dest='oops', **kwargs):
            """Thin Action wrapper.

            Args:
              args: Passed directly to argparse.Action.
              kwargs: Passed directly to argparse.Action.
            """
            self.old_dest = dest
            if dest in self.FILTERS:
                kwargs['default'] = list()
                kwargs['dest'] = 'filters'
            elif dest in self.ORDERINGS:
                kwargs['default'] = list()
                kwargs['dest'] = 'orderings'
            elif dest in self.NUMERIC:
                kwargs['default'] = list()
                kwargs['dest'] = 'numerics'
            elif dest in self.GROUPINGS:
                kwargs['default'] = list()
                kwargs['dest'] = 'groupings'
            else:
                kwargs['dest'] = dest

            super().__init__(*args, **kwargs)

        def __call__(
                self,
                parser: argparse.ArgumentParser,
                namespace: argparse.Namespace,
                values: str,
                option_string: str | None = None):

            # Add the --flag=values to the appropriate dest type/group.
            vars(namespace)[self.dest].append((self.old_dest, values))

    bm_flags = ctx.get_shared_parser('bookmarks_optional')

    parser = ctx.register_command(show, parents=[bm_flags])
    f_mv = 'FIELD'
    fv_mv = 'FIELD:VALUE'
    parser.add_argument(
        '-q', '--query', action='count', default=0, help='Show SQL query.')
    parser.add_argument(
        '-L',
        '--list-fields',
        action='count',
        default=0,
        help='List supported fields.')

    # Numerical based flags
    parser.add_argument(
        '-l',
        '--limit',
        action=QueryBuilder,
        metavar='LIMIT',
        help='Limit the number of results.')

    # Filters
    parser.add_argument(
        '--lt',
        action=QueryBuilder,
        metavar=fv_mv,
        help='Filter portals where FIELD is less than VALUE.')
    parser.add_argument(
        '--le',
        action=QueryBuilder,
        metavar=fv_mv,
        help='Filter portals where FIELD is less than or equal to VALUE.')
    parser.add_argument(
        '--gt',
        action=QueryBuilder,
        metavar=fv_mv,
        help='Filter portals where FIELD is greater than VALUE.')
    parser.add_argument(
        '--ge',
        action=QueryBuilder,
        metavar=fv_mv,
        help='Filter portals where FIELD is greater than or equal to VALUE.')
    parser.add_argument(
        '--in',
        action=QueryBuilder,
        metavar=fv_mv,
        help=(
            'Filter portals where FIELD is equal to VALUE.  If specified'
            ' multiple times for the same FIELD, all matches will be passed.'
        ))
    parser.add_argument(
        '--not-in',
        action=QueryBuilder,
        metavar=fv_mv,
        help=(
            'Filter portals where FIELD is equal to VALUE.  If specified'
            ' multiple times for the same FIELD, all matches will be removed.'
        ))

    # Ordering
    parser.add_argument(
        '--asc',
        action=QueryBuilder,
        metavar=f_mv,
        help='Sort portals by FIELD in ascending order.')
    parser.add_argument(
        '--desc',
        action=QueryBuilder,
        metavar=f_mv,
        help='Sort portals by FIELD in descending order.')

    parser.add_argument(
        '--group-by',
        action=QueryBuilder,
        metavar=f_mv,
        help=(
            'Group portals by the specified fields.  Grouping does NOT'
            ' imply ordering.'))


def show(args: argparse.Namespace) -> int:
    """Show portals selected, sorted and grouped by constraints.

    Many fields can be used to define the constraints.  The fields can be
    found using the --list-fields flag.

    Some fields will always be present, however, others may be controlled by
    other command sets.  For example, the values from the "address-type-*"
    commands will show up here depending on visibility set there.

    Filter flags take a "FIELD:VALUE" argument, where the name of the field is
    separated by a literal colon (:) character.  In most cases, if a field is
    repeated for the same filter, the most restrictive one will take
    precedence, in others, they will be additive.  If you need fancier
    reports, a separate SQL reporting engine may be necessary.

    They can also be exported to a BOOKMARKS file.

    Hint: Multiple BOOKMARKS could be generated then the 'merge' command could
    be used to combine them.
    """
    try:
        return _show_impl(args)
    except Error as exc:
        print(exc)
    return 1


def _show_impl(args: argparse.Namespace) -> int:
    """Implementation for the `show` command."""
    dbc = args.dbc

    constraints: list[str] = list()

    stmt = _init_select(dbc)
    field_map = dict(
        (key, value)
        for key, value in stmt.exported_columns.items()
        if not isinstance(
            getattr(value, 'table', None),
            database.sqlalchemy.sql.schema.Table))

    if args.list_fields:
        print('\n'.join(field_map.keys()))
        return 0

    stmt = _apply_filters(stmt, args, constraints, field_map)
    stmt = _apply_numerics(stmt, constraints, args)
    stmt = _apply_orderings(stmt, args, field_map)

    group_by = _assemble_groups(args, field_map)

    if args.query:
        print(
            stmt.compile(
                dbc.session.get_bind(),
                compile_kwargs={'literal_binds': True}))
        return 0

    portals: bookmarks.Portals = dict()
    groups = collections.defaultdict(list)

    for row in dbc.session.execute(stmt).mappings():
        group = ', '.join(fmt.format_map(row) for fmt in group_by)
        portal = row.PortalV2.to_iitc()
        groups[group].append(portal)
        portals[portal['guid']] = portal

    text_output = list()
    text_output.append(
        f'Matching portals: {len(portals)}\n'
        f'  {", ".join(constraints)}')
    for group in groups:
        section = ''
        if group:
            section += f'Group: {group}\n\n'
        entries = (SHOW_FORMAT.format_map(portal) for portal in groups[group])
        section += '\n\n'.join(entries)
        text_output.append(section)

    print('\n\n=======\n\n'.join(text_output))
    if args.bookmarks:
        bookmarks.save(portals, args.bookmarks)

    return 0


def _init_select(dbc: database.Database) -> Statement:
    """Generate an initial SELECT statement."""
    sqla = database.sqlalchemy

    # XXX: We explicitly set the type_ on certain columns.  This is so that
    # the "literal_binds" option knows how to render the output when showing a
    # query that has bindparams in it (e.g., IN clauses).
    guid = database.PortalV2.guid.label('guid')
    label = database.PortalV2.label.label('label')
    first_seen = sqla.sql.func.date(
        database.PortalV2.first_seen,
        'unixepoch',
        'localtime',
        type_=sqla.Unicode).label('first-seen')
    last_seen = sqla.sql.func.date(
        database.PortalV2.last_seen,
        'unixepoch',
        'localtime',
        type_=sqla.Unicode).label('last-seen')

    cols = tuple(
        sqla.func.max(
            sqla.case(
                (
                    database.AddressTypeValueAssociation.type == typ,
                    database.AddressTypeValueAssociation.value
                ))).label(typ.replace('_', '-'))
        for typ in _visible_address_types(dbc))

    atva = sqla.select(
        database.AddressTypeValueAssociation.latlng,
        *cols).group_by(database.AddressTypeValueAssociation.latlng).subquery(
            name='atva')

    return sqla.select(
        guid, label, first_seen, last_seen, atva,
        database.PortalV2).outerjoin(
            atva, database.PortalV2.latlng == atva.c.latlng)


# XXX: The following dictionaries are cascading rather than nested because the
# version of mypy being used was getting the wrong types for the operator.*
# functions.  Also, by cascading rather than parallel, they are less likely to
# get out of sync.
SCALAR_OPR_TO_STR_MAP = {
    'gt': '>',
    'ge': '>=',
    'lt': '<',
    'le': '<=',
}

SCALAR_STR_TO_FUNC_MAP = {
    '>': operator.gt,
    '>=': operator.ge,
    '<': operator.lt,
    '<=': operator.le,
}

LIST_OP_MAP = {
    'in': 'in_',
    'not_in': 'not_in',
}


def _apply_filters(
        stmt: Statement, args: argparse.Namespace, constraints: list[str],
        field_map) -> Statement:
    """Apply filter clauses to the statement, update "constraints"."""
    sqla = database.sqlalchemy

    params: dict[str, list[str]] = collections.defaultdict(list)
    for opr, field_value in args.filters:
        field, value = _parse_field_value(field_value, field_map.keys())
        column = field_map[field]
        if opr in SCALAR_OPR_TO_STR_MAP:
            op_str = SCALAR_OPR_TO_STR_MAP[opr]
            stmt = stmt.where(SCALAR_STR_TO_FUNC_MAP[op_str](column, value))
            constraints.append(f'{_make_title(field)} {op_str} {value}')
        elif opr in LIST_OP_MAP:
            op_str = LIST_OP_MAP[opr]
            key = f'{opr}=={field}'
            params[key].append(value)
            if len(params[key]) == 1:
                this_op = getattr(column, op_str)
                stmt = stmt.where(
                    this_op(
                        sqla.sql.expression.bindparam(key, expanding=True)))
                constraints.append(f'{_make_title(field)} {opr} ({{{key}}})')
        else:
            raise NotImplementedError(f'Unsupported operator: {opr}')

    _update_constraints_placeholders(constraints, params)
    return stmt.params(params)


def _update_constraints_placeholders(
        constraints: list[str], params: dict[str, list[str]]):
    """Some clauses (e.g., IN), have placeholders, update them in place."""

    # At this point, assuming that all params are lists of strings.
    processed_params = dict(
        (key, ', '.join(values)) for key, values in params.items())
    for pos, item in enumerate(constraints):
        constraints[pos] = item.format_map(processed_params)


def _apply_numerics(
        stmt: Statement, constraints: list[str],
        args: argparse.Namespace) -> Statement:
    """Apply numeric based clauses to the statement, update "constraints"."""
    for opr, value in args.numerics:
        this_op = getattr(stmt, opr, None)
        if this_op:
            stmt = this_op(value)
            constraints.append(f'{_make_title(opr)} {value}')
        else:
            raise NotImplementedError(f'Unsupported operator: {opr}')

    return stmt


def _apply_orderings(
        stmt: Statement, args: argparse.Namespace, field_map) -> Statement:
    """Apply ordering based clauses to the statement."""
    for opr, field in args.orderings:
        _validate_field(field, field_map.keys())
        column = field_map[field]
        this_op = getattr(column, opr)
        if this_op:
            stmt = stmt.order_by(this_op())
        else:
            raise NotImplementedError(f'Unsupported operator: {opr}')

    return stmt


def _assemble_groups(args: argparse.Namespace, field_map) -> list[str]:
    """Assemble a list of formatting strings for use by report grouping."""
    group_by: list[str] = list()

    for _, field in args.groupings:
        _validate_field(field, field_map.keys())
        fmt = f'{_make_title(field)}: {{{field}}}'
        group_by.append(fmt)

    return group_by


def _make_title(field: str) -> str:
    """Turn a "field-name" into "Field Name"."""
    table = str.maketrans('-', ' ')
    return field.translate(table).title()


def _parse_field_value(arg: str,
                       valid_fields: ValidFields) -> tuple[str, str]:
    """Parse the common FIELD:VALUE pairing."""
    field, value = arg.split(':', 1)
    _validate_field(field, valid_fields)
    return field, value


def _validate_field(field: str, valid_fields: ValidFields):
    """Ensure the field is valid, raising Error if not."""
    if field not in valid_fields:
        raise Error(f'Unknown field: {field}')


def _visible_address_types(dbc: database.Database) -> tuple[str, ...]:
    """Fetch user acceptable address types."""
    stmt = database.sqlalchemy.select(database.AddressType)\
               .where(database.AddressType.visibility != 'hide')\
               .order_by(database.AddressType.type)

    return tuple(
        str(row.AddressType.type) for row in dbc.session.execute(stmt))
