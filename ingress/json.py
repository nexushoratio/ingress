"""Utilities to work with JSON files."""

from __future__ import annotations

import json
import os
import tempfile
import time
import typing

if typing.TYPE_CHECKING:  # pragma: no cover
    import argparse

    from mundane import app

_JSON_DUMP_OPTS = {
    'indent': 2,
    'sort_keys': True,
}


def mundane_shared_flags(ctx: app.ArgparseApp):
    """Register shared flags."""
    parser = ctx.new_shared_parser('file')
    parser.add_argument(
        '-f',
        '--filename',
        action='store',
        required=True,
        help='Any arbitrary file argument.')


def mundane_commands(ctx: app.ArgparseApp):
    """Register commands."""
    file_flags = ctx.get_shared_parser('file')

    ctx.register_command(clean, parents=[file_flags])


def load(json_name):
    """Load a utf8-encoded json file."""
    with open(json_name, encoding='utf-8') as handle:
        data = json.load(handle)
    return data


def save(out_name, data):
    """Atomically save a utf8-encoded json file."""
    newname = f'{out_name}.{time.strftime("%Y-%m-%dT%H:%M")}'
    with tempfile.NamedTemporaryFile(prefix='ingress_data', mode='w', dir='.',
                                     encoding='utf-8',
                                     delete=False) as handle:
        json.dump(data, handle, **_JSON_DUMP_OPTS)

    try:
        os.rename(out_name, newname)
    except OSError:
        pass
    os.rename(handle.name, out_name)


def clean(args: argparse.Namespace) -> int:
    """(V) Clean and format a json file."""
    data = load(args.filename)
    save(args.filename, data)

    return 0


def save_by_size(data, size, pattern):
    """Save contents from a list into a series of file of a certain size."""
    # Assume that each item in the list is roughly the same size in the file
    test_string = json.dumps(data, **_JSON_DUMP_OPTS)
    number_needed = len(test_string) // size + 1
    rough_limit = len(test_string) // number_needed
    rough_count = len(data) // number_needed
    width = len(str(number_needed))

    for count in range(number_needed):
        subdata = data[:rough_count]
        del data[:rough_count]
        while data:
            item = data.pop(0)
            subdata.append(item)
            subsize = len(json.dumps(subdata, **_JSON_DUMP_OPTS))
            if subsize > rough_limit:
                break
        filename = pattern.format(size=size, width=width, count=count)
        print(filename)
        save(filename, subdata)
