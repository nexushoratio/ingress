"""Tests for bookmarks.py"""

import unittest

from ingress import bookmarks


class ExistingFolderTest(unittest.TestCase):

    def test_basic(self):
        self.assertTrue(bookmarks.ExistingFolder)


class MundaneSharedFlagsTest(unittest.TestCase):

    def test_basic(self):
        self.assertTrue(bookmarks.mundane_shared_flags)


class MundaneCommandsTest(unittest.TestCase):

    def test_basic(self):
        self.assertTrue(bookmarks.mundane_commands)


class FlattenTest(unittest.TestCase):

    def test_basic(self):
        self.assertTrue(bookmarks.flatten)


class LoadTest(unittest.TestCase):

    def test_basic(self):
        self.assertTrue(bookmarks.load)


class SaveTest(unittest.TestCase):

    def test_basic(self):
        self.assertTrue(bookmarks.save)


class SaveFromGuidsTest(unittest.TestCase):

    def test_basic(self):
        self.assertTrue(bookmarks.save_from_guids)


class FindMissingLabelsTest(unittest.TestCase):

    def test_basic(self):
        self.assertTrue(bookmarks.find_missing_labels)


class MergeTest(unittest.TestCase):

    def test_basic(self):
        self.assertTrue(bookmarks.merge)


class FolderListTest(unittest.TestCase):

    def test_basic(self):
        self.assertTrue(bookmarks.folder_list)


class FolderAddTest(unittest.TestCase):

    def test_basic(self):
        self.assertTrue(bookmarks.folder_add)


class FolderSetTest(unittest.TestCase):

    def test_basic(self):
        self.assertTrue(bookmarks.folder_set)


class FolderClearTest(unittest.TestCase):

    def test_basic(self):
        self.assertTrue(bookmarks.folder_clear)


class FolderDelTest(unittest.TestCase):

    def test_basic(self):
        self.assertTrue(bookmarks.folder_del)


class PlaceListTest(unittest.TestCase):

    def test_basic(self):
        self.assertTrue(bookmarks.place_list)


class PlaceAddTest(unittest.TestCase):

    def test_basic(self):
        self.assertTrue(bookmarks.place_add)


class PlaceSetTest(unittest.TestCase):

    def test_basic(self):
        self.assertTrue(bookmarks.place_set)


class PlaceDelTest(unittest.TestCase):

    def test_basic(self):
        self.assertTrue(bookmarks.place_del)


class MapListTest(unittest.TestCase):

    def test_basic(self):
        self.assertTrue(bookmarks.map_list)


class MapAddTest(unittest.TestCase):

    def test_basic(self):
        self.assertTrue(bookmarks.map_add)


class MapSetTest(unittest.TestCase):

    def test_basic(self):
        self.assertTrue(bookmarks.map_set)


class MapDelTest(unittest.TestCase):

    def test_basic(self):
        self.assertTrue(bookmarks.map_del)


class PortalListTest(unittest.TestCase):

    def test_basic(self):
        self.assertTrue(bookmarks.portal_list)


class PortalAddTest(unittest.TestCase):

    def test_basic(self):
        self.assertTrue(bookmarks.portal_add)


class PortalSetTest(unittest.TestCase):

    def test_basic(self):
        self.assertTrue(bookmarks.portal_set)


class PortalDelTest(unittest.TestCase):

    def test_basic(self):
        self.assertTrue(bookmarks.portal_del)


class ReadTest(unittest.TestCase):

    def test_basic(self):
        self.assertTrue(bookmarks.read_)


class WriteTest(unittest.TestCase):

    def test_basic(self):
        self.assertTrue(bookmarks.write_)


class PrepareFolderTest(unittest.TestCase):

    def test_basic(self):
        self.assertTrue(bookmarks.prepare_folder)


class NewTest(unittest.TestCase):

    def test_basic(self):
        self.assertTrue(bookmarks.new)


if __name__ == '__main__':  # pragma: no cover
    unittest.main()
