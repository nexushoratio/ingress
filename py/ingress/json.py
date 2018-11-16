"""Utilities to work with JSON files."""

from __future__ import absolute_import

import codecs
import json
import os
import tempfile
import time


def load(json_name):
    """Load a utf8-encoded json file."""
    data = json.load(codecs.open(json_name, encoding='utf-8'))
    return data


def save(db_name, data):
    """Atomically save a utf8-encoded json file."""
    newname = '%s.%s' % (db_name, time.strftime('%Y-%m-%dT%H:%M'))
    tmp_fd, tmp_filename = tempfile.mkstemp(prefix='ingress_data', dir='.')
    os.close(tmp_fd)
    tmp_handle = codecs.open(tmp_filename, 'w', encoding='utf-8')
    json.dump(data, tmp_handle, indent=2, sort_keys=True)
    tmp_handle.close()
    try:
        os.rename(db_name, newname)
    except OSError:
        pass
    os.rename(tmp_filename, db_name)


def clean(args, dbc):
    """Clean and format a json file."""
    del dbc
    data = load(args.filename)
    save(args.filename, data)
