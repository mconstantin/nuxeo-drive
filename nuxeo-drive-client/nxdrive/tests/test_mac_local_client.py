__author__ = 'loopingz'

import os
import sys
import tempfile
import shutil

from common_unit_test import UnitTestCase
from nxdrive.osi import AbstractOSIntegration
from unittest import SkipTest, skipIf, skip

if sys.platform == 'darwin':
    from nxdrive.tests.mac_local_client import MacLocalClient

TEST_FILE = "cat.jpg"
DUP_TEST_FILE = "cat__1.jpg"


class TestMacSpecific(UnitTestCase):

    '''
    Test that if Finder is using the file we postpone the sync
    '''
    def test_finder_in_use(self):
        if not AbstractOSIntegration.is_mac():
            raise SkipTest('Not relevant on Linux or Windows')
        self.engine_1.start()
        self.wait_sync(wait_for_async=True)
        self.local_client_1.make_file('/', u'File.txt',
                                      content=u'Some Content 1'.encode('utf-8'))

        # Emulate the Finder in use flag
        OSX_FINDER_INFO_ENTRY_SIZE = 32
        key = (OSX_FINDER_INFO_ENTRY_SIZE)*[0]
        key[0] = 0x62
        key[1] = 0x72
        key[2] = 0x6F
        key[3] = 0x6B
        key[4] = 0x4D
        key[5] = 0x41
        key[6] = 0x43
        key[7] = 0x53
        import xattr
        xattr.setxattr(self.local_client_1._abspath(u'/File.txt'), xattr.XATTR_FINDERINFO_NAME, bytes(bytearray(key)))

        # The file should not be synced and there have no remote id
        self.wait_sync(wait_for_async=True, fail_if_timeout=False, timeout=10)
        info = self.local_client_1.get_remote_id(u'/File.txt')
        self.assertIsNone(info)

        # Remove the Finder flag
        self.local_client_1.remove_remote_id(u'/File.txt', xattr.XATTR_FINDERINFO_NAME)

        # The sync process should now handle the file and sync it
        self.wait_sync(wait_for_async=True, fail_if_timeout=False, timeout=10)
        info = self.local_client_1.get_remote_id(u'/File.txt')
        self.assertIsNotNone(info)


class TestMacClient(UnitTestCase):

    def setUp(self):
        super(TestMacClient, self).setUp()
        self.resource_dir = self.get_test_resources_path()
        self.local_client = MacLocalClient(self.local_nxdrive_folder_1)
        self.test_file = os.path.join(self.resource_dir, TEST_FILE)
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.test_dir)
        super(TestMacClient, self).tearDown()

    @skipIf(sys.platform != 'darwin', 'test is only for Mac')
    def test_copy_to_dir(self):
        self.local_client.copy(self.test_file, self.test_dir)
        self.assertTrue(os.path.exists(os.path.join(self.test_dir, TEST_FILE)), 'copy does not exist')
        self.assertTrue(os.path.exists(os.path.join(self.resource_dir, TEST_FILE)), 'original does not exist')

    @skipIf(sys.platform != 'darwin', 'test is only for Mac')
    def test_copy_source_file_does_not_exist(self):
        missing_test_file = os.path.join(self.resource_dir, 'foo.jpg')
        with self.assertRaises(IOError) as cm:
            self.local_client.copy(missing_test_file, self.test_dir)

    @skipIf(sys.platform != 'darwin', 'test is only for Mac')
    def test_copy_src_dir_does_not_exist(self):
        missing_test_file = os.path.join(self.resource_dir + '_1', TEST_FILE)
        with self.assertRaises(IOError) as cm:
            self.local_client.copy(missing_test_file, self.test_dir)

    # @skipIf(sys.platform != 'darwin', 'test is only for Mac')
    @skip('LocalClient._abspath_deduped method does not work for paths outside base_folder, TBD')
    def test_duplicate_file(self):
        # make a copy first
        self.local_client.copy(self.test_file, self.test_dir)
        self.local_client.duplicate_file(os.path.join(self.test_dir, TEST_FILE))
        self.assertTrue(os.path.exists(os.path.join(self.test_dir, TEST_FILE)), 'original does not exist')
        self.assertTrue(os.path.exists(os.path.join(self.test_dir, DUP_TEST_FILE)), 'duplicate does not exist')

    @skipIf(sys.platform != 'darwin', 'test is only for Mac')
    def test_duplicate_file_does_not_exist(self):
        missing_test_file = os.path.join(self.resource_dir, 'foo.jpg')
        with self.assertRaises(IOError) as cm:
            self.local_client.duplicate_file(missing_test_file)

    @skipIf(sys.platform != 'darwin', 'test is only for Mac')
    def test_move(self):
        # make a copy first
        self.local_client.copy(self.test_file, self.test_dir)
        # create a subdirectory
        os.makedirs(os.path.join(self.test_dir, 'temp'))
        # move file to the subdirectory
        self.local_client.move(os.path.join(self.test_dir, TEST_FILE), os.path.join(self.test_dir, 'temp'))
        self.assertTrue(os.path.exists(os.path.join(self.test_dir, 'temp', TEST_FILE)), 'copy does not exist')
        self.assertFalse(os.path.exists(os.path.join(self.test_dir, TEST_FILE)), 'original still exists')

    @skipIf(sys.platform != 'darwin', 'test is only for Mac')
    def test_move_with_name(self):
        # make a copy first
        self.local_client.copy(self.test_file, self.test_dir)
        # create a subdirectory
        os.makedirs(os.path.join(self.test_dir, 'temp'))
        # move file to the subdirectory
        self.local_client.move(os.path.join(self.test_dir, TEST_FILE), os.path.join(self.test_dir, 'temp'),
                               name='cat1.jpg')
        self.assertTrue(os.path.exists(os.path.join(self.test_dir, 'temp', 'cat1.jpg')), 'copy does not exist')
        self.assertFalse(os.path.exists(os.path.join(self.test_dir, TEST_FILE)), 'original still exists')

    @skipIf(sys.platform != 'darwin', 'test is only for Mac')
    def test_move_dst_dir_does_not_exist(self):
        with self.assertRaises(IOError) as cm:
            self.local_client.move(os.path.join(self.test_dir, TEST_FILE), os.path.join(self.test_dir, 'temp'))

    @skipIf(sys.platform != 'darwin', 'test is only for Mac')
    def test_move_source_file_does_not_exist(self):
        missing_test_file = os.path.join(self.resource_dir, 'foo.jpg')
        with self.assertRaises(IOError) as cm:
            self.local_client.move(missing_test_file, self.test_dir)

    @skipIf(sys.platform != 'darwin', 'test is only for Mac')
    def test_rename(self):
        # make a copy first
        self.local_client.copy(self.test_file, self.test_dir)
        # rename the file copy
        self.local_client.rename(os.path.join(self.test_dir, TEST_FILE), "dog.jpg")
        self.assertTrue(os.path.exists(os.path.join(self.test_dir, "dog.jpg")), 'rename does not exist')
        self.assertFalse(os.path.exists(os.path.join(self.test_dir, TEST_FILE)), 'original still exists')

    @skipIf(sys.platform != 'darwin', 'test is only for Mac')
    def test_delete(self):
        # make a copy first
        self.local_client.copy(self.test_file, self.test_dir)
        # delete the file copy
        self.local_client.delete(os.path.join(self.test_dir, TEST_FILE))
        self.assertFalse(os.path.exists(os.path.join(self.test_dir, TEST_FILE)), 'original still exists')
