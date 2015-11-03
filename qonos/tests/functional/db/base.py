# vim: tabstop=4 shiftwidth=4 softtabstop=4

#    Copyright 2013 Rackspace
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

import datetime
import uuid

from oslo_config import cfg

from qonos.common import exception
from qonos.common import timeutils
from qonos.common import utils as qonos_utils
from qonos.openstack.common import uuidutils
from qonos.tests.unit import utils as unit_utils
from qonos.tests import utils as test_utils


TENANT_1 = uuid.uuid4()
TENANT_2 = uuid.uuid4()


CONF = cfg.CONF


# NOTE(ameade): This is set in each individual db test module
db_api = None


class TestDBApi(test_utils.BaseTestCase):

    def setUp(self):
        super(TestDBApi, self).setUp()
        self.db_api = db_api

    def tearDown(self):
        super(TestDBApi, self).setUp()
        self.db_api.reset()

    def test_reset(self):
        fixture = {
            'tenant': str(uuid.uuid4()),
            'action': 'snapshot',
            'minute': '30',
            'hour': '2',
        }
        self.db_api.schedule_create(fixture)
        self.db_api.reset()
        self.assertFalse(self.db_api.schedule_get_all())


class TestSchedulesDBApi(test_utils.BaseTestCase):

    def setUp(self):
        super(TestSchedulesDBApi, self).setUp()
        self.db_api = db_api
        timeutils.set_time_override(datetime.datetime(
            year=2013, month=1, day=1, hour=9, minute=0))
        self._create_schedules()

    def tearDown(self):
        super(TestSchedulesDBApi, self).setUp()
        self.db_api.reset()
        timeutils.clear_time_override()

    def _create_schedules(self):
        fixture = {
            'id': unit_utils.SCHEDULE_UUID1,
            'tenant': str(TENANT_1),
            'action': 'snapshot',
            'minute': 30,
            'hour': 2,
            'next_run': qonos_utils.cron_string_to_next_datetime(30, 2),
            'schedule_metadata': [
                {
                    'key': 'instance_id',
                    'value': 'my_instance_1',
                },
            ],
        }
        self.schedule_1 = self.db_api.schedule_create(fixture)
        fixture = {
            'id': unit_utils.SCHEDULE_UUID2,
            'tenant': str(TENANT_2),
            'action': 'snapshot',
            'minute': 30,
            'hour': 3,
            'next_run': qonos_utils.cron_string_to_next_datetime(30, 3),
        }
        self.schedule_2 = self.db_api.schedule_create(fixture)

    def _create_basic_schedule(self):
        return db_api.schedule_create({'action': 'snapshot',
                                       'tenant': unit_utils.TENANT1})

    def test_schedule_get_all(self):
        schedules = self.db_api.schedule_get_all()
        self.assertEqual(len(schedules), 2)

    def test_schedule_get_all_filter(self):
        filters = {}
        filters['next_run_after'] = self.schedule_1['next_run']
        filters['next_run_before'] = self.schedule_2['next_run']
        filters['tenant'] = str(TENANT_1)
        schedules = self.db_api.schedule_get_all(filter_args=filters)
        self.assertEqual(len(schedules), 1)
        self.assertEqual(schedules[0]['id'], self.schedule_1['id'])

    def test_schedule_get_all_next_run_filters_are_equal(self):
        filters = {}
        filters['next_run_after'] = self.schedule_1['next_run']
        filters['next_run_before'] = self.schedule_1['next_run']
        filters['tenant'] = str(TENANT_1)
        schedules = self.db_api.schedule_get_all(filter_args=filters)
        self.assertEqual(len(schedules), 1)

    def test_schedule_get_all_tenant_filter(self):
        filters = {}
        filters['tenant'] = str(TENANT_1)
        schedules = self.db_api.schedule_get_all(filter_args=filters)
        self.assertEqual(len(schedules), 1)
        self.assertEqual(schedules[0]['id'], self.schedule_1['id'])

    def test_schedule_get_all_instance_id_filter(self):
        filters = {}
        filters['instance_id'] = 'my_instance_1'
        schedules = self.db_api.schedule_get_all(filter_args=filters)
        self.assertEqual(len(schedules), 1)
        self.assertEqual(schedules[0]['id'], self.schedule_1['id'])

    def test_schedule_get_next_run_filters(self):
        filters = {}
        filters['next_run_after'] = self.schedule_1['next_run']
        filters['next_run_before'] = self.schedule_2['next_run']
        schedules = self.db_api.schedule_get_all(filter_args=filters)
        self.assertEqual(len(schedules), 2)

    def test_schedule_get_all_instance_unknown_filter(self):
        filters = {}
        filters['instance_name'] = 'my_instance_1_name'
        schedules = self.db_api.schedule_get_all(filter_args=filters)
        self.assertEqual(len(schedules), 0)

    def test_schedule_get_next_run_before_filter(self):
        filters = {}
        filters['next_run_before'] = self.schedule_1['next_run']
        schedules = self.db_api.schedule_get_all(filter_args=filters)
        self.assertEqual(len(schedules), 1)

    def test_schedule_get_next_run_after_filter(self):
        filters = {}
        filters['next_run_after'] = self.schedule_2['next_run']
        schedules = self.db_api.schedule_get_all(filter_args=filters)
        self.assertEqual(len(schedules), 1)

    def test_schedule_get_all_with_limit(self):
        filters = {}
        filters['limit'] = 1
        schedules = self.db_api.schedule_get_all(filter_args=filters)
        self.assertEqual(len(schedules), 1)

    def test_schedule_get_all_with_marker(self):
        filters = {}
        filters['marker'] = self.schedule_1['id']
        schedules = self.db_api.schedule_get_all(filter_args=filters)
        self.assertEqual(len(schedules), 1)
        expected = [self.schedule_2]
        self.assertEqual(expected, schedules)

    def test_schedule_get_by_id(self):
        fixture = {
            'tenant': str(uuid.uuid4()),
            'action': 'snapshot',
            'minute': 30,
            'hour': 2,
            'schedule_metadata': [
                {
                    'key': 'instance_id',
                    'value': 'my_instance',
                },
            ],
        }
        expected = self.db_api.schedule_create(fixture)
        actual = self.db_api.schedule_get_by_id(expected['id'])
        self.assertEqual(actual['tenant'], fixture['tenant'])
        self.assertEqual(actual['action'], fixture['action'])
        self.assertEqual(actual['minute'], fixture['minute'])
        self.assertEqual(actual['hour'], fixture['hour'])
        metadata = actual['schedule_metadata']
        self.assertEqual(len(metadata), 1)
        self.assertEqual(metadata[0]['key'],
                         fixture['schedule_metadata'][0]['key'])
        self.assertEqual(metadata[0]['value'],
                         fixture['schedule_metadata'][0]['value'])
        self.assertNotEqual(actual['created_at'], None)
        self.assertNotEqual(actual['updated_at'], None)

    def test_schedule_get_by_id_not_found(self):
        schedule_id = str(uuid.uuid4())
        self.assertRaises(exception.NotFound,
                          self.db_api.schedule_get_by_id, schedule_id)

    def test_schedule_create_no_action(self):
        fixture = {
            'tenant': unit_utils.TENANT1,
        }
        self.assertRaises(exception.MissingValue,
                          self.db_api.schedule_create, fixture)

    def test_schedule_create_no_tenant(self):
        fixture = {
            'action': 'snapshot',
        }
        self.assertRaises(exception.MissingValue,
                          self.db_api.schedule_create, fixture)

    def test_schedule_create(self):
        fixture = {
            'tenant': str(uuid.uuid4()),
            'action': 'snapshot',
            'minute': 30,
            'hour': 2,
            'schedule_metadata': [
                {
                    'key': 'instance_id',
                    'value': 'my_instance',
                },
            ],
        }
        schedule = self.db_api.schedule_create(fixture)
        self.assertTrue(uuidutils.is_uuid_like(schedule['id']))
        self.assertEqual(schedule['tenant'], fixture['tenant'])
        self.assertEqual(schedule['action'], fixture['action'])
        self.assertEqual(schedule['minute'], fixture['minute'])
        self.assertEqual(schedule['hour'], fixture['hour'])
        metadata = schedule['schedule_metadata']
        self.assertEqual(len(metadata), 1)
        self.assertEqual(metadata[0]['key'],
                         fixture['schedule_metadata'][0]['key'])
        self.assertEqual(metadata[0]['value'],
                         fixture['schedule_metadata'][0]['value'])
        self.assertNotEqual(schedule['created_at'], None)
        self.assertNotEqual(schedule['updated_at'], None)

    def test_schedule_update(self):
        fixture = {
            'id': str(uuid.uuid4()),
            'tenant': str(uuid.uuid4()),
            'action': 'snapshot',
            'minute': 30,
            'hour': 2,
        }
        schedule = self.db_api.schedule_create(fixture)
        fixture = {'hour': 3}
        timeutils.set_time_override()
        timeutils.advance_time_seconds(2)
        updated_schedule = self.db_api.schedule_update(schedule['id'], fixture)
        timeutils.clear_time_override()

        self.assertTrue(uuidutils.is_uuid_like(schedule['id']))
        self.assertEqual(updated_schedule['tenant'], schedule['tenant'])
        self.assertEqual(updated_schedule['action'], schedule['action'])
        self.assertEqual(updated_schedule['minute'], schedule['minute'])
        self.assertEqual(updated_schedule['hour'], fixture['hour'])
        self.assertEqual(updated_schedule['created_at'],
                         schedule['created_at'])
        self.assertNotEqual(updated_schedule['updated_at'],
                            schedule['updated_at'])

    def test_schedule_update_remove_metadata(self):
        fixture = {
            'id': str(uuid.uuid4()),
            'tenant': str(uuid.uuid4()),
            'action': 'snapshot',
            'minute': 30,
            'hour': 2,
            'schedule_metadata': [
                {
                    'key': 'instance_id',
                    'value': 'my_instance',
                },
            ],
        }
        schedule = self.db_api.schedule_create(fixture)
        fixture = {
            'schedule_metadata': [],
        }

        timeutils.set_time_override()
        timeutils.advance_time_seconds(2)
        updated_schedule = self.db_api.schedule_update(schedule['id'], fixture)
        timeutils.clear_time_override()

        self.assertTrue(uuidutils.is_uuid_like(schedule['id']))
        self.assertEqual(updated_schedule['tenant'], schedule['tenant'])
        self.assertEqual(updated_schedule['action'], schedule['action'])
        self.assertEqual(updated_schedule['minute'], schedule['minute'])
        self.assertEqual(updated_schedule['hour'], schedule['hour'])
        metadata = updated_schedule['schedule_metadata']
        self.assertEqual(len(metadata), 0)
        # updated child metadata collection doesn't update the parent schedule
        self.assertEqual(updated_schedule['updated_at'],
                         schedule['updated_at'])

    def test_schedule_update_metadata(self):
        fixture = {
            'id': str(uuid.uuid4()),
            'tenant': str(uuid.uuid4()),
            'action': 'snapshot',
            'minute': 30,
            'hour': 2,
        }
        schedule = self.db_api.schedule_create(fixture)
        fixture = {
            'schedule_metadata': [
                {
                    'key': 'instance_id',
                    'value': 'my_instance',
                },
            ],
        }

        timeutils.set_time_override()
        timeutils.advance_time_seconds(2)
        updated_schedule = self.db_api.schedule_update(schedule['id'], fixture)
        timeutils.clear_time_override()

        self.assertTrue(uuidutils.is_uuid_like(schedule['id']))
        self.assertEqual(updated_schedule['tenant'], schedule['tenant'])
        self.assertEqual(updated_schedule['action'], schedule['action'])
        self.assertEqual(updated_schedule['minute'], schedule['minute'])
        self.assertEqual(updated_schedule['hour'], schedule['hour'])
        metadata = updated_schedule['schedule_metadata']
        self.assertEqual(len(metadata), 1)
        self.assertEqual(metadata[0]['key'],
                         fixture['schedule_metadata'][0]['key'])
        self.assertEqual(metadata[0]['value'],
                         fixture['schedule_metadata'][0]['value'])
        self.assertEqual(updated_schedule['created_at'],
                         schedule['created_at'])
        # updated child metadata collection doesn't update the parent schedule
        self.assertEqual(updated_schedule['updated_at'],
                         schedule['updated_at'])

    def test_schedule_test_and_set_next_run(self):
        fixture = {
            'id': str(uuid.uuid4()),
            'tenant': str(uuid.uuid4()),
            'action': 'snapshot',
            'minute': 30,
            'hour': 2,
        }
        new_next_run = timeutils.utcnow()
        schedule = self.db_api.schedule_create(fixture)
        self.db_api.schedule_test_and_set_next_run(
            schedule['id'], None, new_next_run)

        updated_schedule = self.db_api.schedule_get_by_id(schedule['id'])
        self.assertEqual(updated_schedule['next_run'], new_next_run)

    def test_schedule_test_and_set_next_run_with_expected(self):
        fixture = {
            'id': str(uuid.uuid4()),
            'tenant': str(uuid.uuid4()),
            'action': 'snapshot',
            'minute': 30,
            'hour': 2,
        }
        new_next_run = timeutils.utcnow()
        schedule = self.db_api.schedule_create(fixture)
        self.db_api.schedule_test_and_set_next_run(
            schedule['id'], schedule.get('next_run'), new_next_run)

        updated_schedule = self.db_api.schedule_get_by_id(schedule['id'])
        self.assertEqual(updated_schedule['next_run'], new_next_run)

    def test_schedule_test_and_set_next_run_invalid(self):
        fixture = {
            'id': str(uuid.uuid4()),
            'tenant': str(uuid.uuid4()),
            'action': 'snapshot',
            'minute': 30,
            'hour': 2,
        }
        bad_expected_next_run = timeutils.utcnow()
        timeutils.advance_time_seconds(10)
        schedule = self.db_api.schedule_create(fixture)
        self.assertRaises(exception.NotFound,
                          self.db_api.schedule_test_and_set_next_run,
                          schedule['id'], bad_expected_next_run,
                          timeutils.utcnow())

    def test_schedule_delete(self):
        schedules = self.db_api.schedule_get_all()
        self.assertEqual(len(schedules), 2)
        self.db_api.schedule_delete(self.schedule_1['id'])
        schedules = self.db_api.schedule_get_all()
        self.assertEqual(len(schedules), 1)

    def test_schedule_delete_not_found(self):
        schedule_id = str(uuid.uuid4())
        self.assertRaises(exception.NotFound, self.db_api.schedule_delete,
                          schedule_id)

    def test_medadata_created_with_schedule(self):
        fixture = {
            'tenant': str(uuid.uuid4()),
            'action': 'snapshot',
            'minute': 30,
            'hour': 2,
            'schedule_metadata': [
                {
                    'key': 'instance_id',
                    'value': 'my_instance',
                },
            ],
        }
        schedule = self.db_api.schedule_create(fixture)
        metadata = self.db_api.schedule_meta_get_all(schedule['id'])
        self.assertEqual(len(metadata), 1)
        self.assertEqual(metadata[0]['key'],
                         fixture['schedule_metadata'][0]['key'])
        self.assertEqual(metadata[0]['value'],
                         fixture['schedule_metadata'][0]['value'])

    def test_metadata_create(self):
        schedule = self._create_basic_schedule()
        fixture = {'key': 'key1', 'value': 'value1'}
        meta = db_api.schedule_meta_create(schedule['id'], fixture)
        self.assertEqual(meta['schedule_id'], schedule['id'])
        self.assertEqual(meta['key'], fixture['key'])
        self.assertEqual(meta['value'], fixture['value'])
        self.assertNotEqual(meta['created_at'], None)
        self.assertNotEqual(meta['updated_at'], None)
        self.assertNotEqual(meta['id'], None)

    def test_metadata_create_duplicate(self):
        schedule = self._create_basic_schedule()
        fixture = {'key': 'key1', 'value': 'value1'}
        db_api.schedule_meta_create(schedule['id'], fixture)
        fixture = {'key': 'key1', 'value': 'value1'}

        self.assertRaises(exception.Duplicate, db_api.schedule_meta_create,
                          schedule['id'], fixture)

    def test_metadata_get_all(self):
        schedule = self._create_basic_schedule()
        fixture1 = {'key': 'key1', 'value': 'value1'}
        db_api.schedule_meta_create(schedule['id'], fixture1)
        fixture2 = {'key': 'key2', 'value': 'value2'}
        db_api.schedule_meta_create(schedule['id'], fixture2)
        metadata = db_api.schedule_meta_get_all(schedule['id'])
        self.assertEqual(len(metadata), 2)
        for element in metadata:
            self.assertNotEqual(element['id'], None)
            self.assertEqual(element['schedule_id'], schedule['id'])
            self.assertNotEqual(element['created_at'], None)
            self.assertNotEqual(element['updated_at'], None)
            self.assertEqual(element['schedule_id'], schedule['id'])

        self.assertDbMetaInList(metadata, fixture1)
        self.assertDbMetaInList(metadata, fixture2)

    def test_metadata_get_all_no_meta_create(self):
        schedule = self._create_basic_schedule()
        metadata = db_api.schedule_meta_get_all(schedule['id'])
        self.assertEqual(len(metadata), 0)

    def test_metadata_delete(self):
        schedule = self._create_basic_schedule()
        fixture = {'key': 'key1', 'value': 'value1'}
        meta = db_api.schedule_meta_create(schedule['id'], fixture)
        db_api.schedule_meta_delete(schedule['id'], fixture['key'])
        metadata = db_api.schedule_meta_get_all(schedule['id'])
        self.assertEqual(0, len(metadata))
        self.assertFalse(meta in metadata)

    def test_metadata_delete_not_found(self):
        schedule = self._create_basic_schedule()
        fixture = {'key': 'key1', 'value': 'value1'}
        db_api.schedule_meta_create(schedule['id'], fixture)
        db_api.schedule_meta_delete(schedule['id'], fixture['key'])
        self.assertRaises(exception.NotFound, db_api.schedule_meta_delete,
                          schedule['id'], fixture['key'])

    def test_metadata_update(self):
        schedule = self._create_basic_schedule()
        fixture = [{'key': 'foo', 'value': 'bar'}]
        actual = db_api.schedule_metadata_update(schedule['id'], fixture)

        self.assertEqual(actual[0]['key'], fixture[0]['key'])
        self.assertEqual(actual[0]['value'], fixture[0]['value'])
        self.assertEqual(actual[0]['schedule_id'], schedule['id'])
        self.assertTrue(actual[0]['created_at'])
        self.assertTrue(actual[0]['updated_at'])
        self.assertTrue(actual[0]['id'])

    def test_metadata_update_no_change(self):
        schedule = self._create_basic_schedule()
        fixture = [{'key': 'foo', 'value': 'bar'}]
        actual = db_api.schedule_metadata_update(schedule['id'], fixture)

        fixture = [{'key': 'foo', 'value': 'bar'}]
        actual = db_api.schedule_metadata_update(schedule['id'], fixture)

        self.assertEqual(actual[0]['key'], fixture[0]['key'])
        self.assertEqual(actual[0]['value'], fixture[0]['value'])
        self.assertEqual(actual[0]['schedule_id'], schedule['id'])
        self.assertTrue(actual[0]['created_at'])
        self.assertTrue(actual[0]['updated_at'])
        self.assertTrue(actual[0]['id'])

    def test_metadata_update_delete(self):
        schedule = self._create_basic_schedule()
        fixture = [{'key': 'foo', 'value': 'bar'},
                   {'key': 'foo2', 'value': 'bar2'}]
        db_api.schedule_metadata_update(schedule['id'], fixture)
        actual = db_api.schedule_meta_get_all(schedule['id'])
        self.assertEqual(len(actual), 2)

        fixture = []
        db_api.schedule_metadata_update(schedule['id'], fixture)
        actual = db_api.schedule_meta_get_all(schedule['id'])
        self.assertEqual(actual, [])

    def test_metadata_update_remove_one_metadata_item(self):
        schedule = self._create_basic_schedule()
        fixture = [{'key': 'foo', 'value': 'bar'},
                   {'key': 'foo2', 'value': 'bar2'}]
        db_api.schedule_metadata_update(schedule['id'], fixture)
        original = db_api.schedule_meta_get_all(schedule['id'])
        self.assertEqual(len(original), 2)

        fixture = [{'key': 'foo', 'value': 'bar'}]
        db_api.schedule_metadata_update(schedule['id'], fixture)
        actual = db_api.schedule_meta_get_all(schedule['id'])
        self.assertEqual(len(actual), 1)
        self.assertEqual(original[0]['key'], fixture[0]['key'])
        self.assertEqual(original[0]['value'], fixture[0]['value'])
        self.assertEqual(original[0]['schedule_id'], schedule['id'])
        self.assertTrue(original[0]['created_at'])
        self.assertTrue(original[0]['updated_at'])
        self.assertTrue(original[0]['id'])

    def test_metadata_update_schedule_not_found(self):
        schedule_id = str(uuid.uuid4())
        self.assertRaises(exception.NotFound, db_api.schedule_metadata_update,
                          schedule_id, {})

    def test_metadata_get_all_not_found_when_schedule_doesnt_exists(self):
        schedule_id = str(uuid.uuid4())
        self.assertRaises(exception.NotFound, db_api.schedule_meta_get_all,
                          schedule_id)


class TestWorkersDBApi(test_utils.BaseTestCase):

    def setUp(self):
        super(TestWorkersDBApi, self).setUp()
        self.db_api = db_api
        self._create_workers()

    def tearDown(self):
        super(TestWorkersDBApi, self).tearDown()
        self.db_api.reset()

    def _create_workers(self):
        fixture_1 = {'host': 'foo',
                     'id': unit_utils.WORKER_UUID1,
                     }
        fixture_2 = {'host': 'bar',
                     'id': unit_utils.WORKER_UUID2,
                     }
        self.worker_1 = self.db_api.worker_create(fixture_1)
        self.worker_2 = self.db_api.worker_create(fixture_2)

    def test_worker_get_all(self):
        workers = self.db_api.worker_get_all()
        self.assertEqual(len(workers), 2)

    def test_worker_get_all_with_limit(self):
        params = {}
        params['limit'] = 1
        workers = self.db_api.worker_get_all(params=params)
        self.assertEqual(len(workers), 1)
        expected = [self.worker_1]
        self.assertEqual(expected, workers)

    def test_worker_get_all_with_marker(self):
        params = {}
        params['marker'] = self.worker_1['id']
        workers = self.db_api.worker_get_all(params=params)
        self.assertEqual(len(workers), 1)
        expected = [self.worker_2]
        self.assertEqual(expected, workers)

    def test_worker_get_by_id(self):
        actual = self.db_api.worker_get_by_id(self.worker_1['id'])
        self.assertEquals(actual['id'], self.worker_1['id'])
        self.assertEquals(actual['created_at'], self.worker_1['created_at'])
        self.assertEquals(actual['updated_at'], self.worker_1['updated_at'])
        self.assertEquals(actual['host'], self.worker_1['host'])

    def test_worker_get_by_id_not_found(self):
        worker_id = str(uuid.uuid4())
        self.assertRaises(exception.NotFound,
                          self.db_api.worker_get_by_id, worker_id)

    def test_worker_create(self):
        fixture = {'host': 'i.am.cowman'}
        worker = self.db_api.worker_create(fixture)
        self.assertTrue(uuidutils.is_uuid_like(worker['id']))
        self.assertEqual(worker['host'], fixture['host'])
        self.assertNotEqual(worker['created_at'], None)
        self.assertNotEqual(worker['updated_at'], None)

    def test_worker_create_with_pid(self):
        fixture = {'host': 'i.am.cowman',
                   'process_id': 12345}
        worker = self.db_api.worker_create(fixture)
        self.assertTrue(uuidutils.is_uuid_like(worker['id']))
        self.assertEqual(worker['host'], fixture['host'])
        self.assertEqual(worker['process_id'], fixture['process_id'])
        self.assertNotEqual(worker['created_at'], None)
        self.assertNotEqual(worker['updated_at'], None)

    def test_worker_delete(self):
        workers = self.db_api.worker_get_all()
        self.assertEqual(len(workers), 2)
        self.db_api.worker_delete(self.worker_1['id'])
        workers = self.db_api.worker_get_all()
        self.assertEqual(len(workers), 1)

    def test_worker_delete_not_found(self):
        worker_id = str(uuid.uuid4())
        self.assertRaises(exception.NotFound,
                          self.db_api.worker_delete, worker_id)


class TestJobsDBApi(test_utils.BaseTestCase):

    def setUp(self):
        super(TestJobsDBApi, self).setUp()
        self.db_api = db_api
        self._create_jobs()

    def tearDown(self):
        super(TestJobsDBApi, self).tearDown()
        self.db_api.reset()

    def _create_jobs(self):
        now = timeutils.utcnow()
        timeout = now + datetime.timedelta(hours=1)
        hard_timeout = now + datetime.timedelta(hours=4)
        fixture = {
            'id': unit_utils.JOB_UUID1,
            'action': 'snapshot',
            'tenant': unit_utils.TENANT1,
            'schedule_id': unit_utils.SCHEDULE_UUID1,
            'worker_id': unit_utils.WORKER_UUID1,
            'status': 'QUEUED',
            'timeout': timeout,
            'hard_timeout': hard_timeout,
            'retry_count': 0,
        }
        self.job_1 = self.db_api.job_create(fixture)

        fixture = {
            'id': unit_utils.JOB_UUID2,
            'action': 'snapshot',
            'tenant': unit_utils.TENANT1,
            'schedule_id': unit_utils.SCHEDULE_UUID2,
            'worker_id': unit_utils.WORKER_UUID2,
            'status': 'ERROR',
            'timeout': timeout,
            'hard_timeout': hard_timeout,
            'retry_count': 0,
        }
        self.job_2 = self.db_api.job_create(fixture)

    def _create_basic_job(self):
        now = timeutils.utcnow()
        timeout = now + datetime.timedelta(hours=1)
        hard_timeout = now + datetime.timedelta(hours=4)
        return db_api.job_create({'action': 'snapshot',
                                  'timeout': timeout,
                                  'hard_timeout': hard_timeout,
                                  'tenant': unit_utils.TENANT1
                                  })

    def test_job_create_no_action(self):
        fixture = {
            'tenant': unit_utils.TENANT1,
        }
        self.assertRaises(exception.MissingValue,
                          self.db_api.job_create, fixture)

    def test_job_create_no_tenant(self):
        fixture = {
            'action': 'snapshot',
        }
        self.assertRaises(exception.MissingValue,
                          self.db_api.job_create, fixture)

    def test_job_create(self):
        now = timeutils.utcnow()
        timeout = now + datetime.timedelta(hours=1)
        hard_timeout = now + datetime.timedelta(hours=4)
        fixture = {
            'action': 'snapshot',
            'tenant': unit_utils.TENANT1,
            'schedule_id': unit_utils.SCHEDULE_UUID2,
            'worker_id': unit_utils.WORKER_UUID2,
            'status': 'queued',
            'timeout': timeout,
            'hard_timeout': hard_timeout,
            'job_metadata': [
                {
                    'key': 'instance_id',
                    'value': 'my_instance',
                },
            ],
        }

        job = self.db_api.job_create(fixture)

        self.assertTrue(uuidutils.is_uuid_like(job['id']))
        self.assertNotEqual(job['created_at'], None)
        self.assertNotEqual(job['updated_at'], None)
        self.assertEqual(job['timeout'], fixture['timeout'])
        self.assertEqual(job['hard_timeout'], fixture['hard_timeout'])
        self.assertEqual(job['schedule_id'], fixture['schedule_id'])
        self.assertEqual(job['worker_id'], fixture['worker_id'])
        self.assertEqual(job['status'], fixture['status'])
        self.assertEqual(job['retry_count'], 0)
        metadata = job['job_metadata']
        self.assertEqual(len(metadata), 1)
        self.assertEqual(metadata[0]['key'],
                         fixture['job_metadata'][0]['key'])
        self.assertEqual(metadata[0]['value'],
                         fixture['job_metadata'][0]['value'])

    def test_job_create_no_worker_assigned(self):
        now = timeutils.utcnow()
        timeout = now + datetime.timedelta(hours=1)
        hard_timeout = now + datetime.timedelta(hours=4)
        fixture = {
            'action': 'snapshot',
            'tenant': unit_utils.TENANT1,
            'schedule_id': unit_utils.SCHEDULE_UUID2,
            'status': 'queued',
            'timeout': timeout,
            'hard_timeout': hard_timeout,
            'job_metadata': [
                {
                    'key': 'instance_id',
                    'value': 'my_instance',
                },
            ],
        }

        job = self.db_api.job_create(fixture)

        self.assertTrue(uuidutils.is_uuid_like(job['id']))
        self.assertNotEqual(job['created_at'], None)
        self.assertNotEqual(job['updated_at'], None)
        self.assertEqual(job['timeout'], fixture['timeout'])
        self.assertEqual(job['hard_timeout'], fixture['hard_timeout'])
        self.assertEqual(job['schedule_id'], fixture['schedule_id'])
        self.assertEqual(job['worker_id'], None)
        self.assertEqual(job['status'], fixture['status'])
        self.assertEqual(job['retry_count'], 0)
        metadata = job['job_metadata']
        self.assertEqual(len(metadata), 1)
        self.assertEqual(metadata[0]['key'],
                         fixture['job_metadata'][0]['key'])
        self.assertEqual(metadata[0]['value'],
                         fixture['job_metadata'][0]['value'])

    def test_jobs_cleanup_hard_timed_out(self):
        jobs = self.db_api.job_get_all()
        self.assertEqual(len(jobs), 2)
        timeutils.set_time_override()
        timeutils.advance_time_delta(datetime.timedelta(hours=4, minutes=1))
        self.db_api._jobs_cleanup_hard_timed_out()
        timeutils.clear_time_override()
        jobs = self.db_api.job_get_all()
        self.assertEqual(len(jobs), 0)

    def test_job_get_all(self):
        jobs = self.db_api.job_get_all()
        self.assertEqual(len(jobs), 2)

    def test_job_get_all_with_limit(self):
        params = {}
        params['limit'] = 1
        jobs = self.db_api.job_get_all(params=params)
        self.assertEqual(len(jobs), 1)
        expected = [self.job_1]
        self.assertEqual(expected, jobs)

    def test_job_get_all_with_marker(self):
        params = {}
        params['marker'] = self.job_1['id']
        jobs = self.db_api.job_get_all(params=params)
        self.assertEqual(len(jobs), 1)
        expected = [self.job_2]
        self.assertEqual(expected, jobs)

    def test_job_get_all_with_schedule_id_filter(self):
        params = {}
        params['schedule_id'] = unit_utils.SCHEDULE_UUID2
        jobs = self.db_api.job_get_all(params=params)
        self.assertEqual(len(jobs), 1)
        expected = [self.job_2]
        self.assertEqual(expected, jobs)

    def test_job_get_all_with_tenant_filter(self):
        now = timeutils.utcnow()
        timeout = now + datetime.timedelta(hours=1)
        hard_timeout = now + datetime.timedelta(hours=4)
        fixture = {
            'action': 'snapshot',
            'tenant': unit_utils.TENANT3,
            'schedule_id': unit_utils.SCHEDULE_UUID2,
            'worker_id': unit_utils.WORKER_UUID2,
            'status': 'queued',
            'timeout': timeout,
            'hard_timeout': hard_timeout,
            'job_metadata': [
                {
                    'key': 'instance_id',
                    'value': 'my_instance',
                },
            ],
        }

        job = self.db_api.job_create(fixture)

        params = {}
        params['tenant'] = unit_utils.TENANT3
        jobs = self.db_api.job_get_all(params=params)
        self.assertEqual(len(jobs), 1)
        expected = [job]
        self.assertEqual(expected, jobs)

    def test_job_get_all_with_action_filter(self):
        now = timeutils.utcnow()
        timeout = now + datetime.timedelta(hours=1)
        hard_timeout = now + datetime.timedelta(hours=4)
        fixture = {
            'action': 'test_action',
            'tenant': unit_utils.TENANT3,
            'schedule_id': unit_utils.SCHEDULE_UUID2,
            'worker_id': unit_utils.WORKER_UUID2,
            'status': 'queued',
            'timeout': timeout,
            'hard_timeout': hard_timeout,
            'job_metadata': [
                {
                    'key': 'instance_id',
                    'value': 'my_instance',
                },
            ],
        }

        job = self.db_api.job_create(fixture)

        params = {}
        params['action'] = 'test_action'
        jobs = self.db_api.job_get_all(params=params)
        self.assertEqual(len(jobs), 1)
        expected = [job]
        self.assertEqual(expected, jobs)

    def test_job_get_all_with_worker_id_filter(self):
        now = timeutils.utcnow()
        timeout = now + datetime.timedelta(hours=1)
        hard_timeout = now + datetime.timedelta(hours=4)
        fixture = {
            'action': 'test_action',
            'tenant': unit_utils.TENANT3,
            'schedule_id': unit_utils.SCHEDULE_UUID2,
            'worker_id': unit_utils.WORKER_UUID3,
            'status': 'queued',
            'timeout': timeout,
            'hard_timeout': hard_timeout,
            'job_metadata': [
                {
                    'key': 'instance_id',
                    'value': 'my_instance',
                },
            ],
        }

        job = self.db_api.job_create(fixture)

        params = {}
        params['worker_id'] = unit_utils.WORKER_UUID3
        jobs = self.db_api.job_get_all(params=params)
        self.assertEqual(len(jobs), 1)
        expected = [job]
        self.assertEqual(expected, jobs)

    def test_job_get_all_with_status_filter(self):
        now = timeutils.utcnow()
        timeout = now + datetime.timedelta(hours=1)
        hard_timeout = now + datetime.timedelta(hours=4)
        fixture = {
            'action': 'test_action',
            'tenant': unit_utils.TENANT3,
            'schedule_id': unit_utils.SCHEDULE_UUID2,
            'worker_id': unit_utils.WORKER_UUID3,
            'status': 'cancelled',
            'timeout': timeout,
            'hard_timeout': hard_timeout,
            'job_metadata': [
                {
                    'key': 'instance_id',
                    'value': 'my_instance',
                },
            ],
        }

        job = self.db_api.job_create(fixture)

        params = {}
        params['status'] = 'cancelled'
        jobs = self.db_api.job_get_all(params=params)
        self.assertEqual(len(jobs), 1)
        expected = [job]
        self.assertEqual(expected, jobs)

    def test_job_get_all_with_timeout_filter(self):
        now = timeutils.utcnow()
        timeout = now + datetime.timedelta(hours=3)
        hard_timeout = now + datetime.timedelta(hours=4)
        fixture = {
            'action': 'test_action',
            'tenant': unit_utils.TENANT3,
            'schedule_id': unit_utils.SCHEDULE_UUID2,
            'worker_id': unit_utils.WORKER_UUID3,
            'status': 'queued',
            'timeout': timeout,
            'hard_timeout': hard_timeout,
            'job_metadata': [
                {
                    'key': 'instance_id',
                    'value': 'my_instance',
                },
            ],
        }

        job = self.db_api.job_create(fixture)

        params = {}
        params['timeout'] = timeout
        jobs = self.db_api.job_get_all(params=params)
        self.assertEqual(len(jobs), 1)
        expected = [job]
        self.assertEqual(expected, jobs)

    def test_job_get_all_with_hard_timeout_filter(self):
        now = timeutils.utcnow()
        timeout = now + datetime.timedelta(hours=3)
        hard_timeout = now + datetime.timedelta(hours=5)
        fixture = {
            'action': 'test_action',
            'tenant': unit_utils.TENANT3,
            'schedule_id': unit_utils.SCHEDULE_UUID2,
            'worker_id': unit_utils.WORKER_UUID3,
            'status': 'queued',
            'timeout': timeout,
            'hard_timeout': hard_timeout,
            'job_metadata': [
                {
                    'key': 'instance_id',
                    'value': 'my_instance',
                },
            ],
        }

        job = self.db_api.job_create(fixture)

        params = {}
        params['hard_timeout'] = hard_timeout
        jobs = self.db_api.job_get_all(params=params)
        self.assertEqual(len(jobs), 1)
        expected = [job]
        self.assertEqual(expected, jobs)

    def test_job_get_by_id(self):
        expected = self.job_1
        actual = self.db_api.job_get_by_id(self.job_1['id'])
        self.assertEqual(actual['schedule_id'], expected['schedule_id'])
        self.assertEqual(actual['worker_id'], expected['worker_id'])
        self.assertEqual(actual['status'], expected['status'])
        self.assertEqual(actual['retry_count'], expected['retry_count'])
        self.assertEqual(actual['action'], expected['action'])
        self.assertEqual(actual['tenant'], expected['tenant'])
        self.assertEqual(actual['timeout'], expected['timeout'])
        self.assertEqual(actual['hard_timeout'], expected['hard_timeout'])

    def test_job_get_by_id_not_found(self):
        self.assertRaises(exception.NotFound,
                          self.db_api.job_get_by_id, str(uuid.uuid4))

    def test_job_updated_at_get_by_id(self):
        expected = self.job_1['updated_at']
        actual = self.db_api.job_updated_at_get_by_id(self.job_1['id'])
        self.assertEqual(actual, expected)

    def test_job_updated_at_get_by_id_job_not_found(self):
        self.assertRaises(exception.NotFound,
                          self.db_api.job_updated_at_get_by_id,
                          str(uuid.uuid4))

    def test_job_update(self):
        fixture = {
            'status': 'error',
            'retry_count': 2,
        }
        old = self.db_api.job_get_by_id(self.job_1['id'])
        self.db_api.job_update(self.job_1['id'], fixture)
        updated = self.db_api.job_get_by_id(self.job_1['id'])

        self.assertEqual(old['schedule_id'], updated['schedule_id'])
        self.assertEqual(old['worker_id'], updated['worker_id'])
        self.assertNotEqual(old['status'], updated['status'])
        self.assertNotEqual(old['retry_count'], updated['retry_count'])

        self.assertEqual(updated['status'], 'error')
        self.assertEqual(updated['retry_count'], 2)

    def test_job_update_metadata(self):
        fixture = {
            'job_metadata': [
                {
                    'key': 'instance_id',
                    'value': 'my_instance',
                },
            ],
        }
        old = self.db_api.job_get_by_id(self.job_1['id'])
        self.db_api.job_update(self.job_1['id'], fixture)
        updated = self.db_api.job_get_by_id(self.job_1['id'])

        self.assertEqual(old['schedule_id'], updated['schedule_id'])
        self.assertEqual(old['worker_id'], updated['worker_id'])
        self.assertEqual(old['status'], updated['status'])
        self.assertEqual(old['retry_count'], updated['retry_count'])

        metadata = updated['job_metadata']
        self.assertEqual(len(old['job_metadata']), 0)
        self.assertEqual(len(metadata), 1)
        self.assertEqual(metadata[0]['key'],
                         fixture['job_metadata'][0]['key'])
        self.assertEqual(metadata[0]['value'],
                         fixture['job_metadata'][0]['value'])

    def test_job_update_remove_metadata(self):
        fixture = {
            'job_metadata': [
                {
                    'key': 'instance_id',
                    'value': 'my_instance',
                },
            ],
        }
        old = self.db_api.job_update(self.job_1['id'], fixture)

        fixture = {'job_metadata': []}
        updated = self.db_api.job_update(self.job_1['id'], fixture)

        self.assertEqual(old['schedule_id'], updated['schedule_id'])
        self.assertEqual(old['worker_id'], updated['worker_id'])
        self.assertEqual(old['status'], updated['status'])
        self.assertEqual(old['retry_count'], updated['retry_count'])

        metadata = updated['job_metadata']
        self.assertEqual(len(old['job_metadata']), 1)
        self.assertEqual(len(metadata), 0)

    def test_job_delete(self):
        self.assertEqual(len(self.db_api.job_get_all()), 2)
        self.db_api.job_delete(self.job_1['id'])
        self.assertEqual(len(self.db_api.job_get_all()), 1)

    def test_job_delete_not_found(self):
        self.assertRaises(exception.NotFound,
                          self.db_api.job_delete, str(uuid.uuid4))

    def test_metadata_create(self):
        job = self._create_basic_job()
        fixture = {'key': 'key1', 'value': 'value1'}
        meta = db_api.job_meta_create(job['id'], fixture)
        self.assertEqual(meta['job_id'], job['id'])
        self.assertEqual(meta['key'], fixture['key'])
        self.assertEqual(meta['value'], fixture['value'])
        self.assertNotEqual(meta['created_at'], None)
        self.assertNotEqual(meta['updated_at'], None)
        self.assertNotEqual(meta['id'], None)

    def test_metadata_create_duplicate(self):
        job = self._create_basic_job()
        fixture = {'key': 'key1', 'value': 'value1'}
        db_api.job_meta_create(job['id'], fixture)
        fixture = {'key': 'key1', 'value': 'value1'}

        self.assertRaises(exception.Duplicate, db_api.job_meta_create,
                          job['id'], fixture)

    def test_metadata_get_all_by_job_id(self):
        job = self._create_basic_job()
        fixture = {'key': 'key1', 'value': 'value1'}
        db_api.job_meta_create(job['id'], fixture)
        fixture = {'key': 'key2', 'value': 'value2'}
        db_api.job_meta_create(job['id'], fixture)
        meta_list = db_api.job_meta_get_all_by_job_id(job['id'])
        self.assertEqual(len(meta_list), 2)

    def test_metadata_get_all_by_job_id_no_meta(self):
        job = self._create_basic_job()
        meta_list = db_api.job_meta_get_all_by_job_id(job['id'])
        self.assertEqual(len(meta_list), 0)

    def test_metadata_update(self):
        job = self._create_basic_job()
        fixture = [{'key': 'foo', 'value': 'bar'}]
        actual = db_api.job_metadata_update(job['id'], fixture)

        self.assertEqual(actual[0]['key'], fixture[0]['key'])
        self.assertEqual(actual[0]['value'], fixture[0]['value'])
        self.assertEqual(actual[0]['job_id'], job['id'])
        self.assertTrue(actual[0]['created_at'])
        self.assertTrue(actual[0]['updated_at'])
        self.assertTrue(actual[0]['id'])

    def test_metadata_update_job_not_found(self):
        job_id = str(uuid.uuid4())
        self.assertRaises(exception.NotFound, db_api.job_metadata_update,
                          job_id, {})


class TestJobsDBGetNextJobApi(test_utils.BaseTestCase):

    def setUp(self):
        super(TestJobsDBGetNextJobApi, self).setUp()
        self.db_api = db_api
        # There was an intermittent test failure and was able to catch
        # this time being one which triggered it.
        tmp = timeutils.parse_isotime('2014-09-05 20:05:56.629128'). \
            replace(tzinfo=None)
        timeutils.set_time_override(tmp)
        # timeutils.set_time_override()
        self._create_job_fixtures()

    def tearDown(self):
        super(TestJobsDBGetNextJobApi, self).tearDown()
        timeutils.clear_time_override()
        self.db_api.reset()

    def _create_job_fixtures(self):
        now = timeutils.utcnow()
        timeout = now + datetime.timedelta(seconds=30)
        hard_timeout = now + datetime.timedelta(seconds=30)
        self.job_fixture_1 = {
            'action': 'snapshot',
            'tenant': unit_utils.TENANT1,
            'schedule_id': unit_utils.SCHEDULE_UUID1,
            'worker_id': None,
            'status': 'QUEUED',
            'timeout': timeout,
            'hard_timeout': hard_timeout,
            'retry_count': 0,
        }

        self.job_fixture_2 = {
            'action': 'snapshot',
            'tenant': unit_utils.TENANT1,
            'schedule_id': unit_utils.SCHEDULE_UUID2,
            'worker_id': unit_utils.WORKER_UUID2,
            'status': 'QUEUED',
            'timeout': timeout,
            'hard_timeout': hard_timeout,
            'retry_count': 0,
        }

        self.job_fixture_3 = {
            'action': 'snapshot',
            'tenant': unit_utils.TENANT1,
            'schedule_id': unit_utils.SCHEDULE_UUID1,
            'worker_id': None,
            'status': 'DONE',
            'timeout': timeout,
            'hard_timeout': hard_timeout,
            'retry_count': 0,
        }

        self.job_fixture_4 = {
            'action': 'snapshot',
            'tenant': unit_utils.TENANT1,
            'schedule_id': unit_utils.SCHEDULE_UUID1,
            'worker_id': None,
            'status': 'CANCELLED',
            'timeout': timeout,
            'hard_timeout': hard_timeout,
            'retry_count': 0,
        }

        self.job_fixture_5 = {
            'action': 'snapshot',
            'tenant': unit_utils.TENANT1,
            'schedule_id': unit_utils.SCHEDULE_UUID1,
            'worker_id': None,
            'status': 'HARD_TIMED_OUT',
            'timeout': timeout,
            'hard_timeout': hard_timeout,
            'retry_count': 0,
        }

        self.job_fixture_6 = {
            'action': 'snapshot',
            'tenant': unit_utils.TENANT1,
            'schedule_id': unit_utils.SCHEDULE_UUID1,
            'worker_id': None,
            'status': 'MAX_RETRIED',
            'timeout': timeout,
            'hard_timeout': hard_timeout,
            'retry_count': 5,
        }

    def _create_jobs(self, gap, *fixtures):
        now = timeutils.utcnow()
        self.jobs = []
        for fixture in fixtures:
            self.jobs.append(self.db_api.job_create(fixture))
            timeutils.advance_time_seconds(gap)
        return now

    def test_get_next_job_unassigned(self):
        now = timeutils.utcnow()
        new_timeout = now + datetime.timedelta(hours=3)

        self._create_jobs(10, self.job_fixture_1, self.job_fixture_2)
        job = db_api.job_get_and_assign_next_by_action('snapshot',
                                                       unit_utils.WORKER_UUID1,
                                                       new_timeout)
        expected = self.jobs[0]
        self.assertEqual(job['id'], expected['id'])
        self.assertEqual(job['worker_id'], unit_utils.WORKER_UUID1)
        self.assertEqual(job['timeout'], new_timeout)
        self.assertEqual(job['hard_timeout'], expected['hard_timeout'])
        self.assertEqual(job['retry_count'], expected['retry_count'] + 1)

    def test_get_next_job_with_version_id_updated(self):
        now = timeutils.utcnow()
        new_timeout = now + datetime.timedelta(hours=3)

        self._create_jobs(10, self.job_fixture_1)

        actual_job = db_api.job_get_by_id(self.jobs[0]['id'])
        actual_job_version_id = actual_job['version_id']
        self.assertIsNotNone(actual_job_version_id)

        job = db_api.job_get_and_assign_next_by_action('snapshot',
                                                       unit_utils.WORKER_UUID1,
                                                       new_timeout)
        expected_job = self.jobs[0]
        self.assertEqual(job['id'], expected_job['id'])
        self.assertEqual(job['worker_id'], unit_utils.WORKER_UUID1)
        self.assertEqual(job['timeout'], new_timeout)
        self.assertEqual(job['hard_timeout'], expected_job['hard_timeout'])
        self.assertEqual(job['retry_count'], expected_job['retry_count'] + 1)

        updated_job_version_id = job['version_id']
        self.assertNotEqual(updated_job_version_id, actual_job_version_id)

    def test_get_next_job_assigned_once_due_to_timeout(self):
        now = timeutils.utcnow()
        timeout = now - datetime.timedelta(hours=1)
        new_timeout = now + datetime.timedelta(hours=3)
        hard_timeout = now + datetime.timedelta(hours=4)
        job_fixture = {
            'action': 'snapshot',
            'tenant': unit_utils.TENANT1,
            'schedule_id': unit_utils.SCHEDULE_UUID2,
            'worker_id': unit_utils.WORKER_UUID2,
            'status': 'queued',
            'timeout': timeout,
            'hard_timeout': hard_timeout,
            'retry_count': 0,
        }

        self._create_jobs(10, job_fixture)
        db_api.job_get_and_assign_next_by_action('snapshot',
                                                 unit_utils.WORKER_UUID1,
                                                 new_timeout)

        job2 = db_api.job_get_and_assign_next_by_action(
            'snapshot', unit_utils.WORKER_UUID1, new_timeout)
        self.assertEqual(job2, None)

    def test_get_next_job_skip_done(self):
        now = timeutils.utcnow()
        new_timeout = now + datetime.timedelta(hours=3)
        self._create_jobs(10, self.job_fixture_3, self.job_fixture_1)
        job = db_api.job_get_and_assign_next_by_action('snapshot',
                                                       unit_utils.WORKER_UUID1,
                                                       new_timeout)
        expected = self.jobs[1]
        self.assertEqual(job['id'], expected['id'])
        self.assertEqual(job['worker_id'], unit_utils.WORKER_UUID1)
        self.assertEqual(job['timeout'], new_timeout)
        self.assertEqual(job['hard_timeout'], expected['hard_timeout'])
        self.assertEqual(job['retry_count'], expected['retry_count'] + 1)

    def test_get_next_job_skip_cancelled(self):
        now = timeutils.utcnow()
        new_timeout = now + datetime.timedelta(hours=3)
        self._create_jobs(10, self.job_fixture_4, self.job_fixture_1)
        job = db_api.job_get_and_assign_next_by_action('snapshot',
                                                       unit_utils.WORKER_UUID1,
                                                       new_timeout)
        expected = self.jobs[1]
        self.assertEqual(job['id'], expected['id'])
        self.assertEqual(job['worker_id'], unit_utils.WORKER_UUID1)
        self.assertEqual(job['timeout'], new_timeout)
        self.assertEqual(job['hard_timeout'], expected['hard_timeout'])
        self.assertEqual(job['retry_count'], expected['retry_count'] + 1)

    def test_get_next_job_skip_hard_timed_out(self):
        now = timeutils.utcnow()
        new_timeout = now + datetime.timedelta(hours=3)
        self._create_jobs(10, self.job_fixture_5, self.job_fixture_1)
        job = db_api.job_get_and_assign_next_by_action('snapshot',
                                                       unit_utils.WORKER_UUID1,
                                                       new_timeout)
        expected = self.jobs[1]
        self.assertEqual(job['id'], expected['id'])
        self.assertEqual(job['worker_id'], unit_utils.WORKER_UUID1)
        self.assertNotEqual(job['status'], 'HARD_TIMED_OUT')
        self.assertEqual(job['status'], expected['status'])
        self.assertEqual(job['timeout'], new_timeout)
        self.assertEqual(job['hard_timeout'], expected['hard_timeout'])
        self.assertEqual(job['retry_count'], expected['retry_count'] + 1)

    def test_get_next_job_timed_out(self):
        now = timeutils.utcnow()
        new_timeout = now + datetime.timedelta(hours=3)
        # Job 1 based on fixture 2 times out in 5 seconds
        self.job_fixture_2['timeout'] = now + datetime.timedelta(seconds=5)
        self.job_fixture_2['worker_id'] = unit_utils.WORKER_UUID2
        self.job_fixture_2['status'] = 'ERROR'
        # Job 2 based on fixture 1 times out in 125 seconds
        self.job_fixture_1['timeout'] = now + datetime.timedelta(seconds=125)
        self.job_fixture_1['worker_id'] = unit_utils.WORKER_UUID2
        self.job_fixture_2['status'] = 'ERROR'
        # Time is advanced by 20 seconds after this call
        self._create_jobs(10, self.job_fixture_2, self.job_fixture_1)
        # Ensures that timeout test time is on the minute between the two
        # job timeouts defined above
        timeutils.set_time_override(now + datetime.timedelta(65))
        now = timeutils.utcnow()
        print("2. now: %s" % str(now))
        job = db_api.job_get_and_assign_next_by_action('snapshot',
                                                       unit_utils.WORKER_UUID1,
                                                       new_timeout)
        print("Job 1: %s" % self.jobs[0]['id'])
        print("Job 1 timeout: %s" % self.jobs[0]['timeout'])
        print("Job 2: %s" % self.jobs[1]['id'])
        print("Job 2 timeout: %s" % self.jobs[1]['timeout'])
        expected = self.jobs[0]
        self.assertEqual(job['id'], expected['id'])
        self.assertEqual(job['worker_id'], unit_utils.WORKER_UUID1)
        self.assertEqual(job['timeout'], new_timeout)
        self.assertEqual(job['hard_timeout'], expected['hard_timeout'])
        self.assertEqual(job['retry_count'], expected['retry_count'] + 1)

    def test_get_next_job_skip_max_retried(self):
        now = timeutils.utcnow()
        new_timeout = now + datetime.timedelta(hours=3)
        self._create_jobs(10, self.job_fixture_6, self.job_fixture_1)
        job = db_api.job_get_and_assign_next_by_action('snapshot',
                                                       unit_utils.WORKER_UUID1,
                                                       new_timeout)
        expected = self.jobs[1]
        self.assertEqual(job['id'], expected['id'])
        self.assertEqual(job['worker_id'], unit_utils.WORKER_UUID1)
        self.assertNotEqual(job['status'], 'MAX_RETRIED')
        self.assertEqual(job['status'], expected['status'])
        self.assertEqual(job['timeout'], new_timeout)
        self.assertEqual(job['hard_timeout'], expected['hard_timeout'])
        self.assertEqual(job['retry_count'], expected['retry_count'] + 1)


class TestJobFaultDBApi(test_utils.BaseTestCase):

    def setUp(self):
        super(TestJobFaultDBApi, self).setUp()
        self.db_api = db_api

    def tearDown(self):
        super(TestJobFaultDBApi, self).tearDown()
        self.db_api.reset()

    def test_job_fault_create_minimal(self):
        fixture = {
            'schedule_id': str(uuid.uuid4()),
            'tenant': str(uuid.uuid4()),
            'worker_id': str(uuid.uuid4()),
            'job_id': str(uuid.uuid4()),
            'action': 'milking',
            }
        job_fault = self.db_api.job_fault_create(fixture)
        self.assertTrue(uuidutils.is_uuid_like(job_fault['id']))
        self.assertEqual(job_fault['schedule_id'], fixture['schedule_id'])
        self.assertEqual(job_fault['tenant'], fixture['tenant'])
        self.assertEqual(job_fault['worker_id'], fixture['worker_id'])
        self.assertEqual(job_fault['job_id'], fixture['job_id'])
        self.assertEqual(job_fault['action'], fixture['action'])
        self.assertNotEqual(job_fault['created_at'], None)
        self.assertNotEqual(job_fault['updated_at'], None)

    def test_job_fault_create_full(self):
        fixture = {
            'schedule_id': str(uuid.uuid4()),
            'tenant': str(uuid.uuid4()),
            'worker_id': str(uuid.uuid4()),
            'job_id': str(uuid.uuid4()),
            'action': 'milking',
            'message': 'There are too many cows here!',
            'job_metadata': 'When were these cows supposed to leave?',
            }
        job_fault = self.db_api.job_fault_create(fixture)
        self.assertTrue(uuidutils.is_uuid_like(job_fault['id']))
        self.assertEqual(job_fault['schedule_id'], fixture['schedule_id'])
        self.assertEqual(job_fault['tenant'], fixture['tenant'])
        self.assertEqual(job_fault['worker_id'], fixture['worker_id'])
        self.assertEqual(job_fault['job_id'], fixture['job_id'])
        self.assertEqual(job_fault['action'], fixture['action'])
        self.assertEqual(job_fault['message'], fixture['message'])
        self.assertEqual(job_fault['job_metadata'], fixture['job_metadata'])
        self.assertNotEqual(job_fault['created_at'], None)
        self.assertNotEqual(job_fault['updated_at'], None)
