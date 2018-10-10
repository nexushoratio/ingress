"""Utilities to work with JSON files."""

import codecs
import json

def load(json_name):
  data = json.load(codecs.open(json_name, encoding='utf-8'))
  return data

def save(db_name, data):
  newname = '%s.%s' % (db_name, time.strftime('%Y-%m-%dT%H:%M'))
  tmp_fd, tmp_filename = tempfile.mkstemp(prefix='ingress_data', dir='.')
  os.close(tmp_fd)
  #tmp_handle = os.fdopen(tmp_fd, 'w')
  tmp_handle = codecs.open(tmp_filename, 'w', encoding='utf-8')
  json.dump(data, tmp_handle, indent=2, sort_keys=True)
  tmp_handle.close()
  try:
    os.rename(db_name, newname)
  except OSError, e:
    pass
  os.rename(tmp_filename, db_name)
