# vim: tabstop=4 shiftwidth=4 softtabstop=4

#    Copyright 2014 Rackspace
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import copy
import datetime
import mock
import traceback as tb

from novaclient import exceptions
from oslo.config import cfg

from qonos.common import exception
from qonos.common import timeutils
from qonos.common import utils as common_utils
import qonos.qonosclient.exception as qonos_ex
from qonos.tests import utils as utils
from qonos.worker.snapshot import snapshot


CONF = cfg.CONF


class TestableSnapshotProcessor(snapshot.SnapshotProcessor):
    def __init__(self, job_fixture, instance_fixture, images_fixture):
        super(TestableSnapshotProcessor, self).__init__()
        self.job = job_fixture
        self.server = instance_fixture
        self.images = images_fixture

        self.notification_calls = []
        self.update_job_calls = []

        self.org_generate_notification = common_utils.generate_notification

    def __enter__(self):
        worker = self._mock_worker()
        self.qonosclient = worker.get_qonos_client()

        self.nova_client = self._mock_nova_client(self.server, self.images)
        nova_client_factory = self._mock_nova_client_factory(self.job,
                                                             self.nova_client)

        self.init_processor(worker, nova_client_factory=nova_client_factory)
        self._mock_notification_calls()

        return self

    def __exit__(self, exc_type, exc_value, traceback):
        common_utils.generate_notification = self.org_generate_notification

    def _mock_worker(self):
        self.qonosclient = mock.MagicMock()

        def update_job(job_id, status, timeout=None, error_message=None):
            job_update = {'job_id': job_id, 'status': status,
                          'timeout': timeout, 'error_message': error_message}
            self.update_job_calls.append(job_update)
            return job_update

        def update_job_metadata(job_id, metadata):
            return metadata

        def get_qonos_client():
            return self.qonosclient

        worker = mock.Mock()
        worker.update_job = update_job
        worker.update_job_metadata = update_job_metadata
        worker.get_qonos_client = get_qonos_client
        return worker

    def _mock_notification_calls(self):
        def generate_notification(context, event_type, payload, level='INFO'):
            msg = {'context': context, 'event_type': event_type,
                   'payload': copy.deepcopy(payload), 'level': level}
            self.notification_calls.append(msg)

        common_utils.generate_notification = generate_notification

    def _mock_nova_client(self, server, images):
        nova_client = mock.MagicMock()

        if images:
            nova_client.servers.create_image = mock.Mock(
                mock.ANY, return_value=images[0].id)

        if images and len(images) == 1:
            nova_client.images.get = mock.Mock(mock.ANY,
                                               return_value=images[0])
        else:
            nova_client.images.get = mock.Mock(mock.ANY, side_effect=images)

        nova_client.servers.get = mock.Mock(mock.ANY, return_value=server)

        nova_client.images.list = mock.Mock(mock.ANY, return_value=images)
        nova_client.rax_scheduled_images_python_novaclient_ext.get = mock.Mock(
            mock.ANY, return_value=server)

        return nova_client

    def _mock_nova_client_factory(self, job, nova_client):
        nova_client_factory = mock.Mock()
        nova_client_factory.get_nova_client = \
            mock.Mock(job, return_value=nova_client)
        return nova_client_factory


class BaseTestSnapshotProcessor(utils.BaseTestCase):

    def setUp(self):
        super(BaseTestSnapshotProcessor, self).setUp()
        self.config(image_poll_interval_sec=0.01, group='snapshot_worker')

    def tearDown(self):
        super(BaseTestSnapshotProcessor, self).tearDown()

    def server_instance_fixture(self, id_, name, retention=1):
        server = mock.Mock()
        server.id = id_
        server.name = name
        server.retention = retention
        return server

    def job_fixture(self, instance_id):
        now = timeutils.utcnow()
        timeout = now + datetime.timedelta(hours=1)
        hard_timeout = now + datetime.timedelta(hours=4)

        fixture = {
            'id': 'JOB_1',
            'schedule_id': 'SCH_1',
            'tenant': 'TENANT1',
            'worker_id': 'WORKER_1',
            'action': 'snapshot',
            'status': 'QUEUED',
            'timeout': timeout,
            'hard_timeout': hard_timeout,
            'retry_count': 0,
            'metadata': {
                'instance_id': instance_id,
                'value': 'my_instance',
            },
        }
        return fixture

    def image_fixture(self, image_id, status, instance_id, metadata_dict=None):
        image = mock.Mock()
        image.id = image_id
        image.status = status
        image.metadata = {
            "org.openstack__1__created_by": "scheduled_images_service",
            "instance_uuid": instance_id
        }
        image.created = datetime.datetime.now()

        if metadata_dict:
            image.metadata.update(metadata_dict)
        return image

    def assert_update_job_statuses(self, processor, expected_job_statuses):
        """
        Asserts the job_statuses used for updating the job while job processing

        :param processor: the snapshot processor that processes the job
        :expected_job_states:
        """
        actual_job_statuses = (map(lambda x: x['status'],
                                   processor.update_job_calls))
        self.assertEqual(expected_job_statuses, actual_job_statuses)

    def assert_job_status_values(self, processor, expected_status_values={}):
        expected_job_status = expected_status_values['status']
        self.assertEqual(expected_job_status, processor.job['status'])

        job_status_update_values = processor.update_job_calls[-1]
        for k, v in expected_status_values.iteritems():
            self.assertEqual(v, job_status_update_values[k])

    def assert_error_job_update_with_timeout(self, processor):
        error_job_update = processor.update_job_calls[-1]
        self.assertIsNotNone(error_job_update['timeout'])
        self.assertIsNotNone(error_job_update['error_message'])

    def assert_job_notification_events(self, processor, expected_events):
        """
        Asserts the notification events generated as a result of job processing

        :param processor: the snapshot processor that processes the job
        :param expected_events: expected notification events to assert.
                            (event_type, severity_level, payload_job_status)
        """
        def extract_notifications(x):
            job_payload = x['payload']['job']
            if processor.job['id'] == job_payload['id']:
                return (x['event_type'],
                        x['level'],
                        x['payload']['job']['status'])
            return None

        actual_events = filter(None, map(extract_notifications,
                                         processor.notification_calls))
        self.assertEqual(expected_events, actual_events)


class TestSnapshotProcessorJobProcessing(BaseTestSnapshotProcessor):

    def test_process_job_with_create_new_image(self):
        server = self.server_instance_fixture('INSTANCE_ID', "test")
        job = self.job_fixture(server.id)
        new_image = self.image_fixture('IMAGE_ID', 'QUEUED', server.id)
        activated_image = self.image_fixture('IMAGE_ID', 'ACTIVE', server.id)
        images = [activated_image]

        with TestableSnapshotProcessor(job, server, images) as processor:
            processor.nova_client.servers.create_image = mock.Mock(
                mock.ANY, return_value=new_image.id)
            self.assertFalse('image_id' in job['metadata'].keys())

            processor.process_job(job)

            self.assertEqual(
                1, processor.nova_client.servers.create_image.call_count)
            self.assertEqual(activated_image.id,
                             job['metadata']['image_id'])
            self.assertEqual('DONE', job['status'])

    def test_process_job_image_exists_with_active_status(self):
        server = self.server_instance_fixture("INSTANCE_ID", "test")
        job = self.job_fixture(server.id)
        existing_image = self.image_fixture('IMAGE_ID', 'ACTIVE', server.id)

        job['metadata']['image_id'] = existing_image.id

        with TestableSnapshotProcessor(job,
                                       server, [existing_image]) as processor:
            processor.process_job(job)

            self.assertEqual(
                processor.nova_client.servers.create_image.call_count, 0)
            self.assertEqual('DONE', job['status'])

    def test_process_job_image_exists_with_failed_status(self):
        server = self.server_instance_fixture("INSTANCE_ID", "test")

        existing_failed_image = self.image_fixture('IMAGE_ID01',
                                                   'DELETED', server.id)
        recreated_active_image = self.image_fixture('IMAGE_ID02',
                                                    'ACTIVE', server.id)
        images = [existing_failed_image, recreated_active_image]

        job = self.job_fixture(server.id)
        job['metadata']['image_id'] = existing_failed_image.id

        with TestableSnapshotProcessor(job, server, images) as processor:
            processor.nova_client.servers.create_image = mock.Mock(
                mock.ANY, return_value=recreated_active_image.id)

            processor.process_job(job)

            self.assertTrue(processor.nova_client.servers.create_image.called)
            self.assertEqual(recreated_active_image.id,
                             job['metadata']['image_id'])
            self.assertEqual('DONE', job['status'])

    def test_process_job_should_error_if_get_existing_image_detail_fails(self):
        server = self.server_instance_fixture('INSTANCE_ID', "test")
        job = self.job_fixture(server.id)
        job['metadata']['image_id'] = 'IMAGE_ID01'

        with TestableSnapshotProcessor(job,
                                       server, []) as processor:
            exc = exceptions.NotFound('Instance not found!!')
            processor.nova_client.images.get = mock.Mock(mock.ANY,
                                                         side_effect=exc)
            processor.process_job(job)

            org_err_msg = tb.format_exception_only(type(exc), exc)
            err_val = {"job_id": job['id'],
                       "image_id": job['metadata']['image_id'],
                       "org_err_msg": org_err_msg}
            expected_err_msg = ("ERROR get_image_id():"
                                " job_id: %(job_id)s, image_id: %(image_id)s"
                                " err:%(org_err_msg)s") % err_val

            self.assert_update_job_statuses(processor, ['PROCESSING', 'ERROR'])
            self.assert_job_status_values(processor, {
                'status': 'ERROR',
                'error_message': expected_err_msg
            })

    def test_process_job_shouldnt_create_img_if_curr_img_status_is_none(self):
        server = self.server_instance_fixture('INSTANCE_ID', "test")
        job = self.job_fixture(server.id)
        images = [
            self.image_fixture('IMAGE_ID01', None, server.id),
            self.image_fixture('IMAGE_ID01', 'ACTIVE', server.id)
        ]
        job['metadata']['image_id'] = 'IMAGE_ID01'

        with TestableSnapshotProcessor(job, server, images) as processor:
            processor.nova_client.images.list = mock.Mock(
                mock.ANY,
                return_value=[self.image_fixture(
                    'IMAGE_ID01', 'ACTIVE', server.id)])
            processor.process_job(job)

            self.assertFalse(processor.nova_client.servers.create_image.called)
            self.assertEqual('DONE', job['status'])

    def test_process_job_should_cancel_if_create_image_fails(self):
        server = self.server_instance_fixture('INSTANCE_ID', "test")
        job = self.job_fixture(server.id)
        images = []

        with TestableSnapshotProcessor(job, server, images) as processor:
            exc = exceptions.NotFound('Instance not found!!')
            processor.nova_client.servers.create_image = mock.Mock(
                mock.ANY, side_effect=exc)

            processor.process_job(job)

            # NOTE(venkatesh): commenting temporarily until we start deleting
            # the schedules. (SHA:1372fc9a8a820f5203eac82a737fcca92af9a67b)
            # processor.qonosclient.delete_schedule.assert_called_once_with(
            #     processor.job['schedule_id'])
            # self.assertEqual('CANCELLED', job['status'])
            self.assert_update_job_statuses(processor, ['PROCESSING', 'ERROR'])

    def test_process_job_should_cancel_if_schedule_not_exist(self):
        server = self.server_instance_fixture("INSTANCE_ID", "test")
        job = self.job_fixture(server.id)

        with TestableSnapshotProcessor(job, server, []) as processor:
            processor.qonosclient.get_schedule = mock.Mock(
                side_effect=qonos_ex.NotFound())

            processor.process_job(job)

            self.assert_update_job_statuses(processor, ['CANCELLED'])
            self.assertEqual('CANCELLED', job['status'])

    def test_process_job_should_cancel_if_instance_not_found(self):
        server = self.server_instance_fixture("INSTANCE_ID", "test")
        job = self.job_fixture(server.id)

        with TestableSnapshotProcessor(job, None, []) as processor:
            exp = exceptions.NotFound(404)
            processor.nova_client.servers.get = mock.Mock(mock.ANY,
                                                          side_effect=exp)
            processor.process_job(job)

            # NOTE(venkatesh): commenting temporarily until we start deleting
            # the schedules. (SHA:1372fc9a8a820f5203eac82a737fcca92af9a67b)
            # self.assertEqual('CANCELLED', job['status'])
            self.assert_update_job_statuses(processor, ['PROCESSING', 'ERROR'])


class TestSnapshotProcessorPolling(BaseTestSnapshotProcessor):

    def test_polling_job_success_on_first_try(self):
        server = self.server_instance_fixture("INSTANCE_ID", "test")
        job = self.job_fixture(server.id)
        images = [self.image_fixture('IMAGE_ID', 'ACTIVE', server.id)]

        with TestableSnapshotProcessor(job, server, images) as processor:
            processor.process_job(job)

            self.assertEqual(0, processor.timeout_count)
            self.assert_update_job_statuses(processor, ['PROCESSING', 'DONE'])
            self.assertEqual('DONE', job['status'])

    def test_polling_job_success_on_retry(self):
        server = self.server_instance_fixture("INSTANCE_ID", "test")
        job = self.job_fixture(server.id)
        images = [self.image_fixture('IMAGE_ID', 'SAVING', server.id),
                  self.image_fixture('IMAGE_ID', 'ACTIVE', server.id)]

        with TestableSnapshotProcessor(job, server, images) as processor:
            processor.process_job(job)

            self.assertEqual(0, processor.timeout_count)
            self.assert_update_job_statuses(processor, ['PROCESSING', 'DONE'])
            self.assertEqual('DONE', job['status'])

    def test_polling_job_failure_on_first_try_for_failed_image_statuses(self):
        server = self.server_instance_fixture("INSTANCE_ID", "test")
        for error_status in snapshot._FAILED_IMAGE_STATUSES:
            job = self.job_fixture(server.id)
            failed_image = self.image_fixture('IMAGE_ID',
                                              error_status, server.id)
            images = [failed_image]

            with TestableSnapshotProcessor(job, server, images) as processor:
                processor.process_job(job)

                self.assertEqual('ERROR', job['status'])
                err_val = {'image_id': failed_image.id,
                           "image_status": failed_image.status,
                           "job_id": job['id']}
                expected_err_msg = (
                    "PollingErr: Got failed image status. Details:"
                    " image_id: %(image_id)s, 'image_status': %(image_status)s"
                    " job_id: %(job_id)s") % err_val

                self.assert_job_status_values(processor, {
                    'status': 'ERROR',
                    'error_message': expected_err_msg
                })

                self.assertEqual(0, processor.timeout_count)
                self.assert_update_job_statuses(processor,
                                                ['PROCESSING', 'ERROR'])
                self.assert_error_job_update_with_timeout(processor)

    def test_polling_job_failure_on_image_status_returned_as_none(self):
        server = self.server_instance_fixture("INSTANCE_ID", "test")
        job = self.job_fixture(server.id)
        job['metadata']['image_id'] = 'IMAGE_ID01'
        image_status = None
        images = [
            self.image_fixture('IMAGE_ID01', image_status, server.id),
            self.image_fixture('IMAGE_ID01', image_status, server.id)
        ]

        with TestableSnapshotProcessor(job, server, images) as processor:
            processor.process_job(job)

            self.assertEqual('ERROR', job['status'])
            err_val = {'image_id': job['metadata']['image_id'],
                       "image_status": None,
                       "job_id": job['id']}
            expected_err_msg = (
                "PollingErr: Got failed image status. Details:"
                " image_id: %(image_id)s, 'image_status': %(image_status)s"
                " job_id: %(job_id)s") % err_val

            self.assert_job_status_values(processor, {
                'status': 'ERROR',
                'error_message': expected_err_msg
            })

            self.assertEqual(0, processor.timeout_count)
            self.assert_update_job_statuses(processor,
                                            ['PROCESSING', 'ERROR'])
            self.assert_error_job_update_with_timeout(processor)

    def test_polling_job_failure_on_failed_image_statuses_while_polling(self):
        server = self.server_instance_fixture("INSTANCE_ID", "test")
        for error_status in snapshot._FAILED_IMAGE_STATUSES:
            job = self.job_fixture(server.id)
            image_id = 'IMAGE_ID'
            images = [self.image_fixture(image_id, 'SAVING', server.id),
                      self.image_fixture(image_id, error_status, server.id)]

            with TestableSnapshotProcessor(job, server, images) as processor:
                processor.process_job(job)

                self.assertEqual(0, processor.timeout_count)

                err_val = {'image_id': image_id,
                           "image_status": error_status,
                           "job_id": job['id']}
                expected_err_msg = (
                    "PollingErr: Got failed image status. Details:"
                    " image_id: %(image_id)s, 'image_status': %(image_status)s"
                    " job_id: %(job_id)s") % err_val

                self.assert_job_status_values(processor, {
                    'status': 'ERROR',
                    'error_message': expected_err_msg
                })

                self.assert_update_job_statuses(processor,
                                                ['PROCESSING', 'ERROR'])
                self.assert_error_job_update_with_timeout(processor)

    def test_polling_job_timeout_after_max_retries(self):
        initial_timeout = -60
        timeout_extension = .000001

        self.config(job_timeout_extension_sec=timeout_extension,
                    group='snapshot_worker')
        self.config(job_timeout_initial_value_sec=initial_timeout,
                    group='snapshot_worker')
        self.config(job_timeout_max_updates=3, group='snapshot_worker')

        server = self.server_instance_fixture("INSTANCE_ID", "test")
        job = self.job_fixture(server.id)
        images = [self.image_fixture('IMAGE_ID', 'QUEUED', server.id),
                  self.image_fixture('IMAGE_ID', 'SAVING', server.id),
                  self.image_fixture('IMAGE_ID', 'SAVING', server.id),
                  self.image_fixture('IMAGE_ID', 'SAVING', server.id)]

        with TestableSnapshotProcessor(job, server, images) as processor:
            processor.process_job(job)
            self.assertEqual(3, processor.timeout_count)
            self.assert_update_job_statuses(
                processor, (['PROCESSING'] * 4 + ['TIMED_OUT']))
            self.assertEqual('TIMED_OUT', job['status'])

    def test_polling_job_timeout_extension_with_max_retries(self):
        timeout_extension = 3600
        job_timeout_max_updates_count = 3

        self.config(job_timeout_extension_sec=timeout_extension,
                    group='snapshot_worker')
        self.config(job_timeout_max_updates=job_timeout_max_updates_count,
                    group='snapshot_worker')
        self.config(job_timeout_initial_value_sec=10800,
                    group='snapshot_worker')

        server = self.server_instance_fixture("INSTANCE_ID", "test")
        job = self.job_fixture(server.id)
        images = [self.image_fixture('IMAGE_ID', 'QUEUED', server.id),
                  self.image_fixture('IMAGE_ID', 'SAVING', server.id),
                  self.image_fixture('IMAGE_ID', 'SAVING', server.id),
                  self.image_fixture('IMAGE_ID', 'SAVING', server.id)]

        now = timeutils.utcnow()
        timeutils.set_time_override(now)
        timeutils.advance_time_delta(
            datetime.timedelta(seconds=timeout_extension))

        try:
            with TestableSnapshotProcessor(job, server, images) as p:
                p.next_timeout = now + p.initial_timeout
                p.next_update = now + p.update_interval

                #NOTE(venkatesh): unfortunately had to use a protected method
                # for testing. Else there seems to be no easier way to test
                # this scenario. we need to fix this as part of refactoring
                # SnapshotJobProcessor.
                while True:
                    try:
                        p._update_job(job['id'], 'PROCESSING')
                    except exception.OutOfTimeException:
                        break
                    timeutils.advance_time_delta(
                        datetime.timedelta(seconds=timeout_extension))

                total_timeout_duration = datetime.timedelta(
                    seconds=(timeout_extension * job_timeout_max_updates_count)
                )
                self.assertEqual(
                    now + (p.initial_timeout +
                           total_timeout_duration),
                    p.next_timeout
                )
                self.assertEqual(3, p.timeout_count)
        finally:
            timeutils.clear_time_override()

    def test_polling_job_is_successful_after_first_timeout(self):
        server = self.server_instance_fixture("INSTANCE_ID", "test")

        initial_timeout = -60
        self.config(job_timeout_initial_value_sec=initial_timeout,
                    group='snapshot_worker')
        self.config(job_timeout_max_updates=3, group='snapshot_worker')

        job = self.job_fixture(server.id)
        images = [self.image_fixture('IMAGE_ID', 'QUEUED', server.id),
                  self.image_fixture('IMAGE_ID', 'ACTIVE', server.id)]

        with TestableSnapshotProcessor(job, server, images) as processor:
            processor.process_job(job)

            self.assertEqual(1, processor.timeout_count)
            self.assert_update_job_statuses(processor,
                                            (['PROCESSING'] * 2 + ['DONE']))
            self.assertEqual('DONE', job['status'])

    def test_polling_job_updates_status_when_time_for_update(self):
        server = self.server_instance_fixture("INSTANCE_ID", "test")

        decrement_for_next_update = -10
        self.config(job_update_interval_sec=decrement_for_next_update,
                    group='snapshot_worker')

        job = self.job_fixture(server.id)
        images = [self.image_fixture('IMAGE_ID', 'QUEUED', server.id),
                  self.image_fixture('IMAGE_ID', 'QUEUED', server.id),
                  self.image_fixture('IMAGE_ID', 'ACTIVE', server.id)]
        with TestableSnapshotProcessor(job, server, images) as processor:
            processor.process_job(job)

            self.assertEqual(0, processor.timeout_count)
            self.assert_update_job_statuses(processor,
                                            (['PROCESSING'] * 3 + ['DONE']))
            self.assertEqual('DONE', job['status'])


class TestSnapshotProcessorRetentionProcessing(BaseTestSnapshotProcessor):

    def test_process_retention_with_retention_as_0_will_delete_schedule(self):
        server = self.server_instance_fixture("INSTANCE_ID", "test",
                                              retention=0)
        job = self.job_fixture(server.id)
        img_snapshot = [self.image_fixture('IMAGE_ID', 'ACTIVE', server.id)]

        with TestableSnapshotProcessor(job, server, img_snapshot) as processor:
            processor.process_job(job)
            self.assertEqual(0, processor.nova_client.images.delete.call_count)
            # NOTE(venkatesh): commenting temporarily until we start deleting
            # the schedules. (SHA:1372fc9a8a820f5203eac82a737fcca92af9a67b)
            # processor.qonosclient.delete_schedule.assert_called_once_with(
            #     job['schedule_id'])
            self.assertEqual('DONE', job['status'])

    def test_process_retention_with_retention_greater_than_zero(self):
        server = self.server_instance_fixture("INSTANCE_ID", "test",
                                              retention=1)
        job = self.job_fixture(server.id)
        img_snapshot = [self.image_fixture('IMAGE_ID', 'ACTIVE', server.id)]

        with TestableSnapshotProcessor(job, server, img_snapshot) as processor:
            processor.nova_client.images.list = mock.Mock(
                mock.ANY, return_value=img_snapshot)

            processor.process_job(job)

            self.assertEqual(0, processor.nova_client.images.delete.call_count)
            self.assertFalse(processor.qonosclient.delete_schedule.called)
            self.assertEqual(img_snapshot[0].id, job['metadata']['image_id'])
            self.assertEqual('DONE', job['status'])

    def test_process_retention_with_images_greater_than_retention(self):
        server = self.server_instance_fixture("INSTANCE_ID", "test",
                                              retention=2)
        job = self.job_fixture(server.id)

        existing_snapshot_images = [
            self.image_fixture('OLD_IMAGE_01', 'ACTIVE', server.id),
            self.image_fixture('OLD_IMAGE_02', 'ACTIVE', server.id),
            self.image_fixture('OLD_IMAGE_03', 'ACTIVE', server.id),
        ]
        current_image = self.image_fixture('IMAGE_ID', 'ACTIVE', server.id)
        all_instance_images = [current_image] + existing_snapshot_images

        with TestableSnapshotProcessor(job, server,
                                       [current_image]) as processor:
            processor.nova_client.images.list = mock.Mock(
                mock.ANY, return_value=all_instance_images)

            processor.process_job(job)

            self.assertEqual(2, processor.nova_client.images.delete.call_count)
            processor.nova_client.images.delete.has_calls(
                [mock.call('OLD_IMAGE_02'), mock.call('OLD_IMAGE_01')])
            self.assertFalse(processor.qonosclient.delete_schedule.called)
            self.assertEqual(current_image.id, job['metadata']['image_id'])
            self.assertEqual('DONE', job['status'])

    def test_process_retention_with_images_lesser_than_retention(self):
        server = self.server_instance_fixture("INSTANCE_ID", "test",
                                              retention=2)
        job = self.job_fixture(server.id)
        existing_snapshot_images = [
            self.image_fixture('OLD_IMAGE_01', 'ACTIVE', server.id),
        ]
        current_image = self.image_fixture('IMAGE_ID', 'ACTIVE', server.id)
        all_instance_images = [current_image] + existing_snapshot_images

        with TestableSnapshotProcessor(job, server,
                                       [current_image]) as processor:
            processor.nova_client.images.list = mock.Mock(
                mock.ANY, return_value=all_instance_images)

            processor.process_job(job)

            self.assertEqual(0, processor.nova_client.images.delete.call_count)
            self.assertEqual(current_image.id, job['metadata']['image_id'])
            self.assertEqual('DONE', job['status'])

    def test_process_retention_only_for_images_with_given_instance(self):
        some_other_server_id = "OTHER_INSTANCE_ID"
        server = self.server_instance_fixture("INSTANCE_ID", "test",
                                              retention=2)
        job = self.job_fixture(server.id)

        existing_snapshot_images = [
            self.image_fixture('OLD_IMAGE_01', 'ACTIVE', server.id),
            self.image_fixture('OLD_IMAGE_XX', 'ACTIVE', some_other_server_id),
            self.image_fixture('OLD_IMAGE_03', 'ACTIVE', server.id),
        ]
        current_image = self.image_fixture('IMAGE_ID', 'ACTIVE', server.id)
        all_instance_images = [current_image] + existing_snapshot_images

        with TestableSnapshotProcessor(job, server,
                                       [current_image]) as processor:
            processor.nova_client.images.list = mock.Mock(
                mock.ANY, return_value=all_instance_images)

            processor.process_job(job)

            self.assertEqual(1, processor.nova_client.images.delete.call_count)
            processor.nova_client.images.delete.has_calls(
                [mock.call('OLD_IMAGE_01')])
            self.assertEqual('DONE', job['status'])

    def test_process_retention_only_for_images_which_are_active(self):
        server = self.server_instance_fixture("INSTANCE_ID", "test",
                                              retention=2)
        job = self.job_fixture(server.id)

        existing_snapshot_images = [
            self.image_fixture('OLD_IMAGE_01', 'QUEUED', server.id),
            self.image_fixture('OLD_IMAGE_02', 'ACTIVE', server.id),
            self.image_fixture('OLD_IMAGE_03', 'DELETED', server.id),
            self.image_fixture('OLD_IMAGE_04', 'ACTIVE', server.id),
        ]
        current_image = self.image_fixture('IMAGE_ID', 'ACTIVE', server.id)
        all_instance_images = [current_image] + existing_snapshot_images

        with TestableSnapshotProcessor(job, server,
                                       [current_image]) as processor:
            processor.nova_client.images.list = mock.Mock(
                mock.ANY, return_value=all_instance_images)

            processor.process_job(job)

            self.assertEqual(1, processor.nova_client.images.delete.call_count)
            processor.nova_client.images.delete.has_calls(
                [mock.call('OLD_IMAGE_02')])
            self.assertEqual('DONE', job['status'])

    def test_process_retention_only_images_created_by_scheduled_images_service(
            self):
        server = self.server_instance_fixture("INSTANCE_ID", "test",
                                              retention=1)
        job = self.job_fixture(server.id)

        existing_snapshot_images = [
            self.image_fixture(
                'OLD_IMAGE_02', 'ACTIVE', server.id, metadata_dict={
                    "org.openstack__1__created_by": "some_other_service"}),
            self.image_fixture(
                'OLD_IMAGE_03', 'ACTIVE', server.id, metadata_dict={
                    "org.openstack__1__created_by": None}),
            self.image_fixture(
                'OLD_IMAGE_04', 'ACTIVE', server.id, metadata_dict={
                    "org.openstack__1__created_by": "scheduled_images_service"
                }),
        ]
        current_image = self.image_fixture('IMAGE_ID', 'ACTIVE', server.id)
        all_instance_images = [current_image] + existing_snapshot_images

        with TestableSnapshotProcessor(job, server,
                                       [current_image]) as processor:
            processor.nova_client.images.list = mock.Mock(
                mock.ANY, return_value=all_instance_images)

            processor.process_job(job)

            self.assertEqual(1, processor.nova_client.images.delete.call_count)
            processor.nova_client.images.delete.has_calls(
                [mock.call('OLD_IMAGE_04')])
            self.assertEqual('DONE', job['status'])

    def test_process_retention_with_bad_retention(self):
        server = self.server_instance_fixture("INSTANCE_ID",
                                              "test", retention='blah')
        job = self.job_fixture(server.id)
        images = [self.image_fixture('IMAGE_ID', 'ACTIVE', server.id)]

        with TestableSnapshotProcessor(job, server, images) as processor:
            processor.process_job(job)

            self.assertEqual(0, processor.nova_client.images.delete.call_count)
            # NOTE(venkatesh): commenting temporarily until we start deleting
            # the schedules. (SHA:1372fc9a8a820f5203eac82a737fcca92af9a67b)
            # self.assertTrue(processor.qonosclient.delete_schedule.called)
            self.assertEqual('DONE', job['status'])


class TestSnapshotProcessorNotifications(BaseTestSnapshotProcessor):

    def test_notifications_on_successful_job_process(self):
        server = self.server_instance_fixture("INSTANCE_ID", "test")
        job = self.job_fixture(server.id)
        images = [self.image_fixture('IMAGE_ID', 'ACTIVE', server.id)]

        with TestableSnapshotProcessor(job, server, images) as processor:
            processor.process_job(job)

            self.assertEqual('DONE', job['status'])
            expected_notification_events = [
                ('qonos.job.run.start', 'INFO', 'QUEUED'),
                ('qonos.job.update', 'INFO', 'PROCESSING'),
                ('qonos.job.run.end', 'INFO', 'DONE')]
            self.assert_job_notification_events(processor,
                                                expected_notification_events)

    def test_notifications_for_retry_job_process(self):
        server = self.server_instance_fixture("INSTANCE_ID", "test")
        job = self.job_fixture(server.id)
        job['status'] = 'PROCESSING'
        images = [self.image_fixture('IMAGE_ID', 'ACTIVE', server.id)]

        with TestableSnapshotProcessor(job, server, images) as processor:
            processor.process_job(job)

            self.assertEqual('DONE', job['status'])
            expected_notifications = [
                ('qonos.job.retry', 'INFO', 'PROCESSING'),
                ('qonos.job.update', 'INFO', 'PROCESSING'),
                ('qonos.job.run.end', 'INFO', 'DONE')]
            self.assert_job_notification_events(processor,
                                                expected_notifications)

    def test_notifications_for_cancelled_job_on_schedule_not_exist(self):
        server = self.server_instance_fixture("INSTANCE_ID", "test")
        job = self.job_fixture(server.id)

        with TestableSnapshotProcessor(job, server, []) as processor:
            processor.qonosclient.get_schedule = mock.Mock(
                side_effect=qonos_ex.NotFound())

            processor.process_job(job)

            self.assertEqual('CANCELLED', job['status'])
            expected_notifications = [
                ('qonos.job.run.start', 'INFO', 'QUEUED'),
                ('qonos.job.failed', 'ERROR', 'CANCELLED')]
            self.assert_job_notification_events(processor,
                                                expected_notifications)

    def test_notifications_for_cancelled_job_on_instance_not_found(self):
        server = self.server_instance_fixture("INSTANCE_ID", "test")
        job = self.job_fixture(server.id)

        with TestableSnapshotProcessor(job, None, []) as processor:
            exp = exceptions.NotFound(404)
            processor.nova_client.servers.get = mock.Mock(mock.ANY,
                                                          side_effect=exp)
            processor.process_job(job)

            # NOTE(venkatesh): commenting temporarily until we start deleting
            # the schedules. (SHA:1372fc9a8a820f5203eac82a737fcca92af9a67b)
            # self.assertEqual('CANCELLED', job['status'])
            # expected_notifications = [
            #     ('qonos.job.run.start', 'INFO', 'QUEUED'),
            #     ('qonos.job.update', 'INFO', 'PROCESSING'),
            #     ('qonos.job.update', 'INFO', 'CANCELLED')]
            self.assertEqual('ERROR', job['status'])
            expected_notifications = [
                ('qonos.job.run.start', 'INFO', 'QUEUED'),
                ('qonos.job.update', 'INFO', 'PROCESSING'),
                ('qonos.job.update', 'ERROR', 'ERROR')]
            self.assert_job_notification_events(processor,
                                                expected_notifications)

    def test_notifications_for_cancelled_job_on_create_image_failure(self):
        server = self.server_instance_fixture('INSTANCE_ID', "test")
        job = self.job_fixture(server.id)
        images = []

        with TestableSnapshotProcessor(job, server, images) as processor:
            exc = exceptions.NotFound('Instance not found!!')
            processor.nova_client.servers.create_image = mock.Mock(
                mock.ANY, side_effect=exc)

            processor.process_job(job)

            # NOTE(venkatesh): commenting temporarily until we start deleting
            # the schedules. (SHA:1372fc9a8a820f5203eac82a737fcca92af9a67b)
            # self.assertEqual('CANCELLED', job['status'])
            # expected_notifications = [
            #     ('qonos.job.run.start', 'INFO', 'QUEUED'),
            #     ('qonos.job.update', 'INFO', 'PROCESSING'),
            #     ('qonos.job.update', 'INFO', 'CANCELLED')]
            self.assertEqual('ERROR', job['status'])
            expected_notifications = [
                ('qonos.job.run.start', 'INFO', 'QUEUED'),
                ('qonos.job.update', 'INFO', 'PROCESSING'),
                ('qonos.job.update', 'ERROR', 'ERROR')]
            self.assert_job_notification_events(processor,
                                                expected_notifications)

    def test_notifications_for_errored_job_on_failed_image_status(self):
        server = self.server_instance_fixture("INSTANCE_ID", "test")
        job = self.job_fixture(server.id)
        failed_image = self.image_fixture('IMAGE_ID', 'KILLED', server.id)
        images = [failed_image]

        with TestableSnapshotProcessor(job, server, images) as processor:
            processor.process_job(job)

            self.assertEqual('ERROR', job['status'])
            err_val = {'image_id': failed_image.id,
                       "image_status": failed_image.status,
                       "job_id": job['id']}
            expected_err_msg = (
                "PollingErr: Got failed image status. Details:"
                " image_id: %(image_id)s, 'image_status': %(image_status)s"
                " job_id: %(job_id)s") % err_val

            self.assert_job_status_values(processor, {
                'status': 'ERROR',
                'error_message': expected_err_msg
            })
            expected_notifications = [
                ('qonos.job.run.start', 'INFO', 'QUEUED'),
                ('qonos.job.update', 'INFO', 'PROCESSING'),
                ('qonos.job.update', 'ERROR', 'ERROR')]
            self.assert_job_notification_events(processor,
                                                expected_notifications)

    def test_notifications_for_timeout_job_after_max_retries(self):
        initial_timeout = -60
        timeout_extension = .000001

        self.config(job_timeout_extension_sec=timeout_extension,
                    group='snapshot_worker')
        self.config(job_timeout_initial_value_sec=initial_timeout,
                    group='snapshot_worker')
        self.config(job_timeout_max_updates=2, group='snapshot_worker')

        server = self.server_instance_fixture("INSTANCE_ID", "test")
        job = self.job_fixture(server.id)
        images = [self.image_fixture('IMAGE_ID', 'QUEUED', server.id),
                  self.image_fixture('IMAGE_ID', 'SAVING', server.id),
                  self.image_fixture('IMAGE_ID', 'SAVING', server.id)]

        with TestableSnapshotProcessor(job, server, images) as processor:
            processor.process_job(job)

            self.assertEqual('TIMED_OUT', job['status'])
            expected_notifications = [
                ('qonos.job.run.start', 'INFO', 'QUEUED'),
                ('qonos.job.update', 'INFO', 'PROCESSING'),
                ('qonos.job.update', 'INFO', 'TIMED_OUT')]
            self.assert_job_notification_events(processor,
                                                expected_notifications)
