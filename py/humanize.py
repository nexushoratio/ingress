#!/usr/bin/python
"""Provide human readable output."""

def binary_size(num):
  """Return size with a suitable 1024 based."""
  for pre in ['bytes', 'KiB', 'MiB', 'GiB', 'TiB', 'PiB', 'EiB', 'ZiB', 'YiB']:
    if num < 1024.0:
      return "%3.1f%s" % (num, pre)
    num /= 1024.0
  return 'BIG'
