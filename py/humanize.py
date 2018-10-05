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

def h_m_s(seconds):
  """Return xh ym zs when given seconds."""
  secs = int(round(seconds))
  res = list()
  mins, s = divmod(secs, 60)

  if s or not mins:
    res.append('%ds' % s)

  if mins:
    hours, m = divmod(mins, 60)
    if m:
      res.append('%dm' % m)
    if hours:
      days, h = divmod(hours, 24)
      if h:
        res.append('%dh' % h)
      if days:
        res.append('%dd' % days)

  res.reverse()
  return ' '.join(res)
