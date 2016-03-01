import os
import sys
import time
import urllib2
import socket
import httplib
from datetime import datetime
from nose.plugins.skip import SkipTest

from nxdrive.tests.common import TEST_WORKSPACE_PATH
from nxdrive.tests.common import OS_STAT_MTIME_RESOLUTION
from nxdrive.tests.common import IntegrationTestCase
from nxdrive.client import LocalClient
from nxdrive.tests.remote_test_client import RemoteTestClient
from nxdrive.client.remote_filtered_file_system_client import RemoteFilteredFileSystemClient

# TODO NXDRIVE-170: refactor
LastKnownState = None


class TestSynchronization(IntegrationTestCase):

    def test_binding_initialization_and_first_sync(self):
        local = self.local_client_1
        remote = self.remote_document_client_1

        # Create some documents in a Nuxeo workspace and bind this server to a
        # Nuxeo Drive local folder
        self.make_server_tree()
        self.setUpDrive_1()

        # The root binding operation does not create the local folder yet.
        self.assertFalse(local.exists('/'))

        # Launch ndrive and check synchronization
        self.ndrive()
        self.assertTrue(local.exists('/'))
        self.assertTrue(local.exists('/Folder 1'))
        self.assertEquals(local.get_content('/Folder 1/File 1.txt'), "aaa")
        self.assertTrue(local.exists('/Folder 1/Folder 1.1'))
        self.assertEquals(local.get_content('/Folder 1/Folder 1.1/File 2.txt'), "bbb")
        self.assertTrue(local.exists('/Folder 1/Folder 1.2'))
        self.assertEquals(local.get_content('/Folder 1/Folder 1.2/File 3.txt'), "ccc")
        self.assertTrue(local.exists('/Folder 2'))
        # Cannot predicte the resolution in advance
        self.assertTrue(remote.get_content(self._duplicate_file_1), "Some content.")
        self.assertTrue(remote.get_content(self._duplicate_file_2), "Other content.")
        if local.get_content('/Folder 2/Duplicated File.txt') == "Some content.":
            self.assertEquals(local.get_content('/Folder 2/Duplicated File__1.txt'), "Other content.")
        else:
            self.assertEquals(local.get_content('/Folder 2/Duplicated File.txt'), "Other content.")
            self.assertEquals(local.get_content('/Folder 2/Duplicated File__1.txt'), "Some content.")
        self.assertEquals(local.get_content('/Folder 2/File 4.txt'), "ddd")
        self.assertEquals(local.get_content('/File 5.txt'), "eee")

        # Unbind root and resynchronize: smoke test
        self.unbind_root(self.ndrive_1_options, self.workspace, self.local_nxdrive_folder_1)
        self.ndrive()

    def test_binding_synchronization_empty_start(self):
        local = self.local_client_1
        remote = self.remote_document_client_1

        # Let's create some documents on the server and launch first synchronization
        self.make_server_tree()
        self.setUpDrive_1(firstSync=True)

        # We should now be fully synchronized
        folder_count, file_count = self.get_local_child_count(self.local_nxdrive_folder_1)
        self.assertEquals(folder_count, 5)
        self.assertTrue(file_count, 7)

        # Wait a bit for file time stamps to increase enough: on OSX HFS+ the
        # file modification time resolution is 1s for instance
        time.sleep(OS_STAT_MTIME_RESOLUTION)

        # Let do some local and remote changes concurrently
        local.delete('/File 5.txt')
        local.update_content('/Folder 1/File 1.txt', 'aaaa')
        local.make_folder('/', 'Folder 4')

        # The remote client use in this test is handling paths relative to
        # the 'Nuxeo Drive Test Workspace'
        remote.update_content('/Folder 1/Folder 1.1/File 2.txt', 'bbbb')
        remote.delete('/Folder 2')
        f3 = remote.make_folder(self.workspace, 'Folder 3')
        remote.make_file(f3, 'File 6.txt', content='ffff')

        # Launch synchronization
        self.wait()
        self.ndrive()

        # We should now be fully synchronized again
        self.assertFalse(remote.exists('/File 5.txt'))
        self.assertEquals(remote.get_content('/Folder 1/File 1.txt'), "aaaa")
        self.assertTrue(remote.exists('/Folder 4'))

        self.assertEquals(local.get_content('/Folder 1/Folder 1.1/File 2.txt'), "bbbb")
        # Let's just check remote document hasn't changed
        self.assertEquals(remote.get_content('/Folder 1/Folder 1.1/File 2.txt'), "bbbb")
        self.assertFalse(local.exists('/Folder 2'))
        self.assertTrue(local.exists('/Folder 3'))
        self.assertEquals(local.get_content('/Folder 3/File 6.txt'), "ffff")

        # Send some binary data that is not valid in utf-8 or ascii
        # (to test the HTTP / Multipart transform layer).
        time.sleep(OS_STAT_MTIME_RESOLUTION)
        local.update_content('/Folder 1/File 1.txt', "\x80")
        remote.update_content('/Folder 1/Folder 1.1/File 2.txt', '\x80')

        self.wait()
        self.ndrive()

        self.assertEquals(remote.get_content('/Folder 1/File 1.txt'), "\x80")
        self.assertEquals(local.get_content('/Folder 1/Folder 1.1/File 2.txt'), "\x80")
        # Let's just check remote document hasn't changed
        self.assertEquals(remote.get_content('/Folder 1/Folder 1.1/File 2.txt'), "\x80")

    def test_single_quote_escaping(self):
        remote = self.remote_document_client_1
        local = LocalClient(self.local_nxdrive_folder_1)
        self.setUpDrive_1(bind_root=False)

        remote.make_folder('/', "APPEL D'OFFRES")
        remote.register_as_root("/APPEL D'OFFRES")
        self.wait()
        self.ndrive()
        self.assertTrue(local.exists("/APPEL D'OFFRES"))

        remote.unregister_as_root("/APPEL D'OFFRES")
        self.wait()
        self.ndrive()
        self.assertFalse(local.exists("/APPEL D'OFFRES"))

    def test_synchronization_modification_on_created_file(self):
        raise SkipTest("WIP in https://jira.nuxeo.com/browse/NXDRIVE-170")
        ctl = self.controller_1
        # Regression test: a file is created locally, then modification is
        # detected before first upload
        ctl.bind_server(self.local_nxdrive_folder_1, self.nuxeo_url,
                        self.user_1, self.password_1)
        ctl.bind_root(self.local_nxdrive_folder_1, self.workspace)
        syn = ctl.synchronizer
        expected_folder = os.path.join(self.local_nxdrive_folder_1,
                                       self.workspace_title)
        self.assertEquals(ctl.list_pending(), [])

        self.wait()
        syn.loop(delay=0.010, max_loops=1)

        # Let's create some document on the client and the server
        local = LocalClient(expected_folder)
        local.make_folder('/', 'Folder')
        local.make_file('/Folder', 'File.txt', content='Some content.')

        # First local scan (assuming the network is offline):
        syn.scan_local(self.local_nxdrive_folder_1)
        self.assertEquals(len(ctl.list_pending()), 2)
        self.assertEquals(ctl.children_states(expected_folder), [
            (u'Folder', 'children_modified'),
        ])
        self.assertEquals(ctl.children_states(expected_folder + '/Folder'), [
            (u'File.txt', u'unknown'),
        ])

        # Wait a bit for file time stamps to increase enough: on most OS
        # the file modification time resolution is 1s
        time.sleep(OS_STAT_MTIME_RESOLUTION)

        # Let's modify it offline and rescan locally
        local.update_content('/Folder/File.txt', content='Some content.')
        syn.scan_local(self.local_nxdrive_folder_1)
        self.assertEquals(len(ctl.list_pending()), 2)
        self.assertEquals(ctl.children_states(expected_folder), [
            (u'Folder', u'children_modified'),
        ])
        self.assertEquals(ctl.children_states(expected_folder + '/Folder'), [
            (u'File.txt', u'locally_modified'),
        ])

        # Assume the computer is back online, the synchronization should occur
        # as if the document was just created and not trigger an update
        self.wait()
        syn.loop(delay=0.010, max_loops=1)
        self.assertEquals(ctl.list_pending(), [])
        self.assertEquals(ctl.children_states(expected_folder), [
            (u'Folder', u'synchronized'),
        ])
        self.assertEquals(ctl.children_states(expected_folder + '/Folder'), [
            (u'File.txt', u'synchronized'),
        ])

    def test_basic_synchronization(self):
        local = self.local_client_1
        remote = self.remote_document_client_1
        self.setUpDrive_1(firstSync=True)

        # Let's create some document on the client and the server
        local.make_folder('/', 'Folder 3')
        self.make_server_tree()

        # Launch ndrive and check synchronization
        self.ndrive()
        self.assertTrue(remote.exists('/Folder 3'))
        self.assertTrue(local.exists('/Folder 1'))
        self.assertTrue(local.exists('/Folder 2'))
        self.assertTrue(local.exists('/File 5.txt'))

    def test_synchronization_loop_skip_errors(self):
        raise SkipTest("WIP in https://jira.nuxeo.com/browse/NXDRIVE-170")
        ctl = self.controller_1
        ctl.bind_server(self.local_nxdrive_folder_1, self.nuxeo_url,
                        self.user_1, self.password_1)
        ctl.bind_root(self.local_nxdrive_folder_1, self.workspace)
        syn = ctl.synchronizer
        expected_folder = os.path.join(self.local_nxdrive_folder_1,
                                       self.workspace_title)

        self.assertEquals(ctl.list_pending(), [])
        self.assertEquals(syn.synchronize(), 0)

        # Perform first scan and sync
        self.wait()
        syn.loop(delay=0, max_loops=3)
        self.assertEquals(ctl.list_pending(), [])
        self.assertEquals(syn.synchronize(), 0)

        # Let's create some document on the client and the server
        local = LocalClient(expected_folder)
        local.make_folder('/', 'Folder 3')
        self.make_server_tree()
        self.wait()

        # Detect the files to synchronize but do not perform the
        # synchronization
        syn.scan_remote(self.local_nxdrive_folder_1)
        syn.scan_local(self.local_nxdrive_folder_1)
        pending = ctl.list_pending()
        self.assertEquals(len(pending), 12)
        self.assertEquals(pending[0].local_name, 'Folder 3')
        self.assertEquals(pending[0].pair_state, 'unknown')
        self.assertEquals(pending[1].remote_name, 'File 5.txt')
        self.assertEquals(pending[1].pair_state, 'remotely_modified')
        self.assertEquals(pending[2].remote_name, 'Folder 1')
        self.assertEquals(pending[2].pair_state, 'remotely_modified')

        # Simulate synchronization errors
        session = ctl.get_session()
        file_5 = session.query(LastKnownState).filter_by(
            remote_name='File 5.txt').one()
        file_5.last_sync_error_date = datetime.utcnow()
        folder_3 = session.query(LastKnownState).filter_by(
            local_name='Folder 3').one()
        folder_3.last_sync_error_date = datetime.utcnow()
        session.commit()

        # Run the full synchronization loop a limited amount of times
        syn.loop(delay=0, max_loops=3)

        # All errors have been skipped, while the remaining docs have
        # been synchronized
        pending = ctl.list_pending()
        self.assertEquals(len(pending), 2)
        self.assertEquals(pending[0].local_name, 'Folder 3')
        self.assertEquals(pending[0].pair_state, 'unknown')
        self.assertEquals(pending[1].remote_name, 'File 5.txt')
        self.assertEquals(pending[1].pair_state, 'remotely_modified')

        # Reduce the skip delay to retry the sync on pairs in error
        syn.error_skip_period = 0.000001
        syn.loop(delay=0, max_loops=3)
        self.assertEquals(ctl.list_pending(), [])
        self.assertEquals(ctl.children_states(expected_folder), [
            (u'File 5.txt', u'synchronized'),
            (u'Folder 1', u'synchronized'),
            (u'Folder 2', u'synchronized'),
            (u'Folder 3', u'synchronized'),
        ])

    def test_synchronization_give_up(self):
        raise SkipTest("WIP in https://jira.nuxeo.com/browse/NXDRIVE-170")
        ctl = self.controller_1

        # Override to only 2 errors
        ctl.get_max_errors = lambda: 2
        ctl.bind_server(self.local_nxdrive_folder_1,
                            self.nuxeo_url, self.user_1, self.password_1)
        ctl.bind_root(self.local_nxdrive_folder_1, self.workspace)
        syn = ctl.synchronizer
        syn.error_skip_period = 1
        expected_folder = os.path.join(self.local_nxdrive_folder_1,
                                       self.workspace_title)

        # Bound root but nothing is synced yet
        self.assertEquals(ctl.list_pending(), [])
        self.assertEquals(syn.synchronize(), 0)

        # Perform first scan and sync
        syn.loop(delay=1, max_loops=2)
        self.assertEquals(ctl.list_pending(), [])
        self.assertEquals(syn.synchronize(), 0)

        # Let's create some document on the client and the server
        local = LocalClient(expected_folder)
        local.make_folder('/', 'Folder 3')
        self.make_server_tree()
        self.wait()

        ctl.remote_filtered_fs_client_factory = RemoteTestClient
        ctl.invalidate_client_cache()
        # First check that socket error doesnt count
        ctl.make_remote_raise(socket.error('Test error'))
        syn.loop(delay=1, max_loops=2)
        self.assertEquals(len(ctl.list_on_errors()), 0)

        # Find various ways to simulate a network or server failure
        error = httplib.HTTPException('Test error')
        error.code = 500
        ctl.make_remote_raise(error)

        # Synchronization does not occur but does not fail either
        syn.loop(delay=1, max_loops=3)

        # All is synchronized
        self.assertEquals(ctl.list_pending(), [])
        self.assertEquals(len(ctl.list_on_errors()), 7)

        # Increase the max number of errors
        ctl.get_max_errors = lambda: 3
        self.assertEquals(len(ctl.list_pending()), 7)
        self.assertEquals(len(ctl.list_on_errors()), 0)

        # Synchronization does not occur but does not fail either
        syn.loop(delay=1, max_loops=2)

        # Everything should be on errors again
        self.assertEquals(ctl.list_pending(), [])
        self.assertEquals(len(ctl.list_on_errors()), 7)

        # Remove faulty client
        ctl.make_remote_raise(None)
        ctl.remote_filtered_fs_client_factory = RemoteFilteredFileSystemClient
        ctl.invalidate_client_cache()

        for doc_pair in ctl.list_on_errors():
            doc_pair.error_count = 0
        # Verify that we will sync now
        self.assertEquals(len(ctl.list_pending()), 7)
        syn.loop(delay=0, max_loops=3)
        # Everything should be ok now
        self.assertEquals(ctl.list_pending(), [])
        self.assertEquals(len(ctl.list_on_errors()), 0)

    def test_synchronization_offline(self):
        raise SkipTest("WIP in https://jira.nuxeo.com/browse/NXDRIVE-170")
        ctl = self.controller_1
        ctl.bind_server(self.local_nxdrive_folder_1, self.nuxeo_url,
                             self.user_1, self.password_1)
        ctl.bind_root(self.local_nxdrive_folder_1, self.workspace)
        syn = ctl.synchronizer
        expected_folder = os.path.join(self.local_nxdrive_folder_1,
                                       self.workspace_title)

        # Bound root but nothing is synced yet
        self.assertEquals(ctl.list_pending(), [])
        self.assertEquals(syn.synchronize(), 0)

        # Perform first scan and sync
        syn.loop(delay=0, max_loops=3)
        self.assertEquals(ctl.list_pending(), [])
        self.assertEquals(syn.synchronize(), 0)

        # Let's create some document on the client and the server
        local = LocalClient(expected_folder)
        local.make_folder('/', 'Folder 3')
        self.make_server_tree()
        self.wait()

        # Find various ways to simulate a network or server failure
        errors = [
            urllib2.URLError('Test error'),
            socket.error('Test error'),
            httplib.HTTPException('Test error'),
        ]
        for error in errors:
            ctl.make_remote_raise(error)
            # Synchronization does not occur but does not fail either
            syn.loop(delay=0, max_loops=1)
            # Only the local change has been detected
            self.assertEquals(len(ctl.list_pending()), 1)

        # Reenable network
        ctl.make_remote_raise(None)
        syn.loop(delay=0, max_loops=2)

        # All is synchronized
        self.assertEquals(ctl.list_pending(), [])
        self.assertEquals(ctl.children_states(expected_folder), [
            (u'File 5.txt', u'synchronized'),
            (u'Folder 1', u'synchronized'),
            (u'Folder 2', u'synchronized'),
            (u'Folder 3', u'synchronized'),
        ])

    def test_conflict_detection_and_renaming(self):
        raise SkipTest("WIP in https://jira.nuxeo.com/browse/NXDRIVE-170")
        ctl = self.controller_1
        ctl.bind_server(self.local_nxdrive_folder_1, self.nuxeo_url,
                        self.user_1, self.password_1)
        ctl.bind_root(self.local_nxdrive_folder_1, self.workspace)
        syn = ctl.synchronizer
        # Fetch the workspace sync root
        syn.loop(delay=0, max_loops=1, no_event_init=True)
        self.assertEquals(ctl.list_pending(), [])

        # Let's create some document on the client and synchronize it.
        local = LocalClient(self.local_nxdrive_folder_1)
        local_path = local.make_file('/' + self.workspace_title,
           'Some File.doc', content="Original content.")
        syn.loop(delay=0, max_loops=1, no_event_init=True)

        # Let's modify it concurrently but with the same content (digest)
        time.sleep(OS_STAT_MTIME_RESOLUTION)
        local.update_content(local_path, 'Same new content.')

        remote_2 = self.remote_document_client_2
        remote_2.update_content('/Some File.doc', 'Same new content.')

        # Let's synchronize and check the conflict handling: automatic
        # resolution will work for this case/
        self.wait()
        syn.loop(delay=0, max_loops=1, no_event_init=True)
        item_infos = local.get_children_info('/' + self.workspace_title)
        self.assertEquals(len(item_infos), 1)
        self.assertEquals(item_infos[0].name, 'Some File.doc')
        self.assertEquals(local.get_content(local_path), 'Same new content.')

        # Let's trigger another conflict that cannot be resolved
        # automatically:
        time.sleep(OS_STAT_MTIME_RESOLUTION)
        local.update_content(local_path, 'Local new content.')

        remote_2 = self.remote_document_client_2
        remote_2.update_content('/Some File.doc', 'Remote new content.')
        self.wait()
        # 2 loops are necessary for full conflict handling
        syn.loop(delay=0, max_loops=2, no_event_init=True)
        item_infos = local.get_children_info('/' + self.workspace_title)
        self.assertEquals(len(item_infos), 2)

        first, second = item_infos
        if first.name == 'Some File.doc':
            version_from_remote, version_from_local = first, second
        else:
            version_from_local, version_from_remote = first, second

        self.assertEquals(version_from_remote.name, 'Some File.doc')
        self.assertEquals(local.get_content(version_from_remote.path),
            'Remote new content.')

        self.assertTrue(version_from_local.name.startswith('Some File ('),
            msg="'%s' was expected to start with 'Some File ('"
                % version_from_local.name)
        self.assertTrue(version_from_local.name.endswith(').doc'),
            msg="'%s' was expected to end with ').doc'"
                % version_from_local.name)
        self.assertEquals(local.get_content(version_from_local.path),
            'Local new content.')

        # Everything is synchronized
        all_states = self.get_all_states()

        self.assertEquals(all_states[:2], [
            (u'/',
             u'synchronized', u'synchronized'),
            (u'/Nuxeo Drive Test Workspace',
             u'synchronized', u'synchronized'),
        ])
        # The filename changes with the date
        self.assertEquals(all_states[2][1:],
            (u'synchronized', u'synchronized'))
        self.assertEquals(all_states[3],
            (u'/Nuxeo Drive Test Workspace/Some File.doc',
             u'synchronized', u'synchronized'))

    def test_synchronize_deep_folders(self):
        if sys.platform.startswith('linux'):
            raise SkipTest("WIP in https://jira.nuxeo.com/browse/NXDRIVE-170")
        # Increase Automation execution timeout for NuxeoDrive.GetChangeSummary
        # because of the recursive parent FileSystemItem adaptation
        self.setUpDrive_1(firstSync=True)

        # Create a file deep down in the hierarchy
        remote = self.remote_document_client_1

        folder_name = '0123456789'
        folder_depth = 40
        folder = '/'
        for _ in range(folder_depth):
            folder = remote.make_folder(folder, folder_name)

        remote.make_file(folder, "File.odt", content="Fake non-zero content.")

        self.wait()
        self.ndrive()

        local = LocalClient(self.local_nxdrive_folder_1)
        expected_folder_path = (
            '/' + self.workspace_title + ('/' + folder_name) * folder_depth)

        expected_file_path = expected_folder_path + '/File.odt'
        self.assertTrue(local.exists(expected_folder_path))
        self.assertTrue(local.exists(expected_file_path))
        self.assertEquals(local.get_content(expected_file_path),
                          "Fake non-zero content.")

        # Delete the nested folder structure on the remote server
        # and synchronize again
        remote.delete('/' + folder_name)

        self.wait()
        self.ndrive()

        self.assertFalse(local.exists(expected_folder_path))
        self.assertFalse(local.exists(expected_file_path))

    def test_create_content_in_readonly_area(self):
        raise SkipTest("WIP in https://jira.nuxeo.com/browse/NXDRIVE-170")
        # Let's bind a the server but no root workspace
        ctl = self.controller_1
        ctl.bind_server(self.local_nxdrive_folder_1, self.nuxeo_url,
                        self.user_1, self.password_1)
        syn = ctl.synchronizer
        self.wait()

        syn.loop(delay=0.1, max_loops=1)
        self.assertEquals(ctl.list_pending(), [])

        # Let's create a subfolder of the main readonly folder
        local = LocalClient(self.local_nxdrive_folder_1)
        local.make_folder('/', 'Folder 3')
        local.make_file('/Folder 3', 'File 1.txt', content='Some content.')
        local.make_folder('/Folder 3', 'Sub Folder 1')
        local.make_file('/Folder 3/Sub Folder 1', 'File 2.txt',
                        content='Some other content.')
        syn.loop(delay=0.1, max_loops=1)

        # Pairs have been created for the subfolder and its content,
        # marked as synchronized
        self.assertEquals(self.get_all_states(get_pair_state=True), [
            (u'/', u'synchronized', u'synchronized', u'synchronized'),
            (u'/Folder 3', u'created', u'unknown', u'unsynchronized'),
            (u'/Folder 3/File 1.txt', u'created', u'unknown',
             u'unsynchronized'),
            (u'/Folder 3/Sub Folder 1', u'created', u'unknown',
             u'unsynchronized'),
            (u'/Folder 3/Sub Folder 1/File 2.txt',
             u'created', u'unknown', u'unsynchronized'),
        ])
        self.assertEquals(ctl.list_pending(), [])

        # Let's create a file in the main readonly folder
        local.make_file('/', 'A file in a readonly folder.txt',
            content='Some Content')
        syn.loop(delay=0.1, max_loops=1)

        # A pair has been created, marked as synchronized
        self.assertEquals(self.get_all_states(get_pair_state=True), [
            (u'/', u'synchronized', u'synchronized', u'synchronized'),
            (u'/A file in a readonly folder.txt',
             u'created', u'unknown', u'unsynchronized'),
            (u'/Folder 3', u'created', u'unknown', u'unsynchronized'),
            (u'/Folder 3/File 1.txt', u'created', u'unknown',
             u'unsynchronized'),
            (u'/Folder 3/Sub Folder 1', u'created', u'unknown',
             u'unsynchronized'),
            (u'/Folder 3/Sub Folder 1/File 2.txt',
             u'created', u'unknown', u'unsynchronized'),
        ])
        self.assertEquals(len(ctl.list_pending(ignore_in_error=300)), 0)

        # Let's create a file and a folder in a folder on which the Write
        # permission has been removed. Thanks to NXP-13119, this permission
        # change will be detected server-side, thus fetched by the client
        # in the remote change summary, and the remote_can_create_child flag
        # on which the synchronizer relies to check if creation is allowed
        # will be set to False and no attempt to create the remote file
        # will be made.

        # Bind root workspace, create local folder and synchronize it remotely
        ctl.bind_root(self.local_nxdrive_folder_1, self.workspace)
        self.wait()
        syn.loop(delay=0.1, max_loops=1)

        local = LocalClient(
            os.path.join(self.local_nxdrive_folder_1, self.workspace_title))
        local.make_folder(u'/', u'Readonly folder')
        syn.loop(delay=0.1, max_loops=1)

        remote = self.remote_document_client_1
        self.assertTrue(remote.exists(u'/Readonly folder'))

        # Check remote_can_create_child flag in pair state
        session = ctl.get_session()
        readonly_folder_state = session.query(LastKnownState).filter_by(
            local_name=u'Readonly folder').one()
        self.assertTrue(readonly_folder_state.remote_can_create_child)

        # Make one sync loop to detect remote folder creation triggered
        # by last synchronization and make sure we get a clean state at
        # next change summary
        self.wait()
        syn.loop(delay=0.1, max_loops=1)
        # Re-fetch folder state as sync loop closes the Session
        readonly_folder_state = session.query(LastKnownState).filter_by(
            local_name=u'Readonly folder').one()
        self.assertTrue(readonly_folder_state.remote_can_create_child)

        # Set remote folder as readonly for test user
        readonly_folder_path = TEST_WORKSPACE_PATH + u'/Readonly folder'
        op_input = "doc:" + readonly_folder_path
        self.root_remote_client.execute("Document.SetACE",
            op_input=op_input,
            user="nuxeoDriveTestUser_user_1",
            permission="Read")
        self.root_remote_client.block_inheritance(readonly_folder_path,
                                                  overwrite=False)

        # Wait to make sure permission change is detected.
        self.wait()
        syn.loop(delay=0.1, max_loops=1)
        # Re-fetch folder state as sync loop closes the Session
        readonly_folder_state = session.query(LastKnownState).filter_by(
            local_name=u'Readonly folder').one()
        self.assertFalse(readonly_folder_state.remote_can_create_child)

        # Try to create a local file and folder in the readonly folder,
        # they should not be created remotely.
        local.make_file(u'/Readonly folder', u'File in readonly folder',
                        u"File content")
        local.make_folder(u'/Readonly folder', u'Folder in readonly folder')
        syn.loop(delay=0.1, max_loops=1)
        self.assertFalse(remote.exists(
            u'/Readonly folder/File in readonly folder'))
        self.assertFalse(remote.exists(
            u'/Readonly folder/Folder in readonly folder'))

    def test_synchronize_special_filenames(self):
        local = self.local_client_1
        remote = self.remote_document_client_1
        self.setUpDrive_1(firstSync=True)

        # Create some remote documents with weird filenames
        folder = remote.make_folder(self.workspace,
            u'Folder with forbidden chars: / \\ * < > ? "')

        self.wait()
        self.ndrive()
        folder_names = [i.name for i in local.get_children_info('/')]
        self.assertEquals(folder_names,
            [u'Folder with forbidden chars- - - - - - - -'])

        # create some file on the server
        remote.make_file(folder,
            u'File with forbidden chars: / \\ * < > ? ".doc',
            content="some content")

        self.wait()
        self.ndrive()

        file_names = [i.name for i in local.get_children_info(
                      local.get_children_info('/')[0].path)]
        self.assertEquals(file_names,
            [u'File with forbidden chars- - - - - - - -.doc'])

    def test_synchronize_deleted_blob(self):
        local = self.local_client_1
        remote = self.remote_document_client_1
        self.setUpDrive_1(firstSync=True)

        # Create a doc with a blob in the remote root workspace
        # then synchronize
        remote.make_file('/', 'test.odt', 'Some content.')

        self.wait()
        self.ndrive()
        self.assertTrue(local.exists('/test.odt'))

        # Delete the blob from the remote doc then synchronize
        remote.delete_content('/test.odt')

        self.wait()
        self.ndrive()
        self.assertFalse(local.exists('/test.odt'))

    def test_synchronize_paged_delete_detection(self):
        raise SkipTest("WIP in https://jira.nuxeo.com/browse/NXDRIVE-170")
        # Initialize a controller with page size = 1 for deleted items
        # detection query
        # TODO NXDRIVE-170: refactor
        #ctl = Controller(self.nxdrive_conf_folder_1, page_size=1)
        ctl = None
        ctl.bind_server(self.local_nxdrive_folder_1, self.nuxeo_url,
                        self.user_1, self.password_1)
        ctl.bind_root(self.local_nxdrive_folder_1, self.workspace)

        # Launch first synchronization
        self.wait()
        syn = ctl.synchronizer
        syn.loop(delay=0.1, max_loops=1)

        # Get local and remote clients
        local = LocalClient(os.path.join(self.local_nxdrive_folder_1,
                                         self.workspace_title))
        remote = self.remote_document_client_1

        # Create a remote folder with 2 children then synchronize
        remote.make_folder('/', 'Remote folder',)
        remote.make_file('/Remote folder', 'Remote file 1.odt',
                         'Some content.')
        remote.make_file('/Remote folder', 'Remote file 2.odt',
                         'Other content.')

        self.wait()
        syn.loop(delay=0.1, max_loops=1)
        self.assertTrue(local.exists('/Remote folder'))
        self.assertTrue(local.exists('/Remote folder/Remote file 1.odt'))
        self.assertTrue(local.exists('/Remote folder/Remote file 2.odt'))

        # Delete remote folder then synchronize
        remote.delete('/Remote folder')

        self.wait()
        syn.loop(delay=0.1, max_loops=1)
        self.assertFalse(local.exists('/Remote folder'))
        self.assertFalse(local.exists('/Remote folder/Remote file 1.odt'))
        self.assertFalse(local.exists('/Remote folder/Remote file 2.odt'))

        # Create a local folder with 2 children then synchronize
        local.make_folder('/', 'Local folder')
        local.make_file('/Local folder', 'Local file 1.odt', 'Some content.')
        local.make_file('/Local folder', 'Local file 2.odt', 'Other content.')

        syn.loop(delay=0.1, max_loops=1)
        self.assertTrue(remote.exists('/Local folder'))
        self.assertTrue(remote.exists('/Local folder/Local file 1.odt'))
        self.assertTrue(remote.exists('/Local folder/Local file 2.odt'))

        # Delete local folder then synchronize
        time.sleep(OS_STAT_MTIME_RESOLUTION)
        local.delete('/Local folder')

        syn.loop(delay=0.1, max_loops=1)
        self.assertFalse(remote.exists('/Local folder'))
        # Wait for async completion as recursive deletion of children is done
        # by the BulkLifeCycleChangeListener which is asynchronous
        self.wait()
        self.assertFalse(remote.exists('/Local folder/Local file 1.odt'))
        self.assertFalse(remote.exists('/Local folder/Local file 2.odt'))

        # Dispose dedicated Controller instantiated for this test
        ctl.dispose()
