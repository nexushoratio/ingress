"""Tests for rtree.py"""

import unittest

from ingress import rtree


class RtreeIndexTest(unittest.TestCase):

    def test_basic(self):
        self.assertTrue(rtree.rtree_index)


if __name__ == '__main__':  # pragma: no cover
    unittest.main()
