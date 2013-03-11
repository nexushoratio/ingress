#!/usr/bin/python
"""Provide human readable output."""

import datetime

def binary_size(num):
  """Return size with a suitable 1024 based."""
  for pre in ['bytes', 'KiB', 'MiB', 'GiB', 'TiB', 'PiB', 'EiB', 'ZiB', 'YiB']:
    if num < 1024.0:
      return "%3.1f%s" % (num, pre)
    num /= 1024.0
  return 'BIG'

def time(seconds):
  """Return hh:mm:ss when given seconds."""
  return str(datetime.timedelta(seconds=seconds))
