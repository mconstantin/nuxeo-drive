'''
Created on 12-Aug-2016

@author: dgraja
'''

from mock import patch
from urllib2 import URLError
import nxdrive
from nxdrive.tests.common_unit_test import log, UnitTestCase
from nxdrive.client.remote_file_system_client import RemoteFileSystemClient


network_error = False
original_get_children_info = RemoteFileSystemClient.get_children_info


def mock_get_children_info(self, *args, **kwargs):
    if network_error:
        # simulate a network error during the call to NuxeoDrive.GetChildren
        raise URLError("Network error simulated for NuxeoDrive.GetChildren ")
    return original_get_children_info(self, *args, **kwargs)


class TestBulkRemoteChanges(UnitTestCase):
    '''
       Test Bulk Remote Changes when network error happen 
    '''
    def setUp(self):
        super(TestBulkRemoteChanges, self).setUp()
        self.last_sync_date = None
        self.last_event_log_id = None
        self.last_root_definitions = None
        # Initialize last event log id (lower bound)
        self.wait()
        self.trace = log.warn
        self.confirm = log.error

    @patch.object(nxdrive.client.remote_file_system_client.RemoteFileSystemClient, 'get_children_info', mock_get_children_info)
    def test_many_changes(self):
        global network_error
        remote_client = self.remote_document_client_1
        local_client = self.local_client_1
        
        self.engine_1.start()
        self.trace("Waiting for Engine to do initialize local folder")
        self.wait_sync(wait_for_async=True)
        
        # create some folders on the server
        self.trace("Creating 3 folders: folder1, folder2, shared ...")
        folder1 = remote_client.make_folder(self.workspace, u"folder1")
        shared = remote_client.make_folder(self.workspace, u"shared")
        folder2 = remote_client.make_folder(self.workspace, u"folder2")
        
        self.trace("Creating files shared/Readme.txt, folder1/file1.txt, folder2/file2.text ...")
        remote_client.make_file(shared, "Readme.txt", "This is a readme file")
        remote_client.make_file(folder1, "file1.txt", "This is a sample file1")
        remote_client.make_file(folder2, "file2.txt", "This is a sample file2")
        
        self.trace("Wait for first round of remote changes to down sync")
        self.wait_sync(wait_for_async=True)
        
        self.confirm("Verify remote contents are downloaded successfully first round: " +
                     "/folder1/file1.txt, /folder2/file2.txt, /shared/Readme.txt")
        self.assertTrue(local_client.exists('/folder1'))
        self.assertTrue(local_client.exists('/folder2'))
        self.assertTrue(local_client.exists('/shared'))
        self.assertTrue(local_client.exists('/folder1/file1.txt'))
        self.assertTrue(local_client.exists('/folder2/file2.txt'))
        self.assertTrue(local_client.exists('/shared/Readme.txt'))

        network_error = True
        self.trace("Making more changes to server side: upload folder1/sample1.txt, upload folder2/sample2.txt, share shared folder")
        remote_client.make_file(folder1, "sample1.txt", "This is a another sample file1")
        self.remote_document_client_2.register_as_root(shared)
        remote_client.delete(shared)
        remote_client.undelete(shared)
#         remote_client.make_file(shared, "more-data.txt", "This is a another shared file")
        remote_client.make_file(folder2, "sample2.txt", "This is a another sample file2")
        
        self.trace("Wait for second round of remote changes to down sync => updates to existing content")
        self.wait_sync(wait_for_async=True)
        
        self.confirm("Verify remote contents are downloaded successfully second round: " +
                     "/folder1/sample1.txt, /folder2/sample2.txt, /shared/more-data.txt")
        self.assertTrue(local_client.exists('/folder1/sample1.txt'))
        self.assertTrue(local_client.exists('/folder2/sample2.txt'))
