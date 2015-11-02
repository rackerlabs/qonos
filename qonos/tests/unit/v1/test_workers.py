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
import webob.exc

from oslo_config import cfg

from qonos.api.v1 import workers
from qonos.common import exception
from qonos.common import timeutils
import qonos.db.simple.api as db_api
from qonos.tests.unit import utils as unit_utils
from qonos.tests import utils as test_utils

WORKER_ATTRS = ['id', 'host']


CONF = cfg.CONF


class TestWorkersApi(test_utils.BaseTestCase):

    def setUp(self):
        super(TestWorkersApi, self).setUp()
        self.controller = workers.WorkersController(db_api=db_api)
        self._create_workers()
        self._create_schedules()
        self._create_jobs()

    def tearDown(self):
        super(TestWorkersApi, self).tearDown()
        db_api.reset()

    def _create_workers(self):
        fixture = {'host': 'foo.cow', 'id': unit_utils.WORKER_UUID1}
        self.worker_1 = db_api.worker_create(fixture)
        fixture = {'host': 'bar.bar', 'id': unit_utils.WORKER_UUID2}
        self.worker_2 = db_api.worker_create(fixture)
        fixture = {'host': 'baz.cow', 'id': unit_utils.WORKER_UUID3}
        self.worker_3 = db_api.worker_create(fixture)
        fixture = {'host': 'qux.bar', 'id': unit_utils.WORKER_UUID4}
        self.worker_4 = db_api.worker_create(fixture)

    def _create_schedules(self):
        fixture = {
            'id': unit_utils.SCHEDULE_UUID1,
            'tenant': unit_utils.TENANT1,
            'action': 'snapshot',
            'minute': '30',
            'hour': '2',
            'next_run': '2012-11-27T02:30:00Z'
        }
        self.schedule_1 = db_api.schedule_create(fixture)
        fixture = {
            'id': unit_utils.SCHEDULE_UUID2,
            'tenant': unit_utils.TENANT2,
            'action': 'snapshot',
            'minute': '30',
            'hour': '2',
            'next_run': '2012-11-27T02:30:00Z',
            'schedule_metadata': [
                {
                    'key': 'instance_id',
                    'value': 'my_instance',
                },
            ],
        }
        self.schedule_2 = db_api.schedule_create(fixture)
        fixture = {
            'id': unit_utils.SCHEDULE_UUID3,
            'tenant': unit_utils.TENANT3,
            'action': 'snapshot',
            'minute': '30',
            'hour': '4',
            'next_run': '2012-11-27T02:30:00Z',
        }
        self.schedule_3 = db_api.schedule_create(fixture)
        fixture = {
            'id': unit_utils.SCHEDULE_UUID4,
            'tenant': unit_utils.TENANT4,
            'action': 'snapshot',
            'minute': '30',
            'hour': '5',
            'next_run': '2012-11-27T02:30:00Z',
        }
        self.schedule_4 = db_api.schedule_create(fixture)

    def _create_jobs(self):
        now = timeutils.utcnow()
        timeout = now + datetime.timedelta(hours=1)
        hard_timeout = now + datetime.timedelta(hours=4)

        fixture = {
            'id': unit_utils.JOB_UUID1,
            'schedule_id': self.schedule_1['id'],
            'tenant': unit_utils.TENANT1,
            'worker_id': None,
            'action': 'snapshot',
            'status': None,
            'timeout': timeout,
            'hard_timeout': hard_timeout,
            'retry_count': 0,
        }
        self.job_1 = db_api.job_create(fixture)
        fixture = {
            'id': unit_utils.JOB_UUID2,
            'schedule_id': self.schedule_2['id'],
            'tenant': unit_utils.TENANT2,
            'worker_id': unit_utils.WORKER_UUID2,
            'action': 'snapshot',
            'status': None,
            'timeout': timeout,
            'hard_timeout': hard_timeout,
            'retry_count': 1,
            'job_metadata': [
                {
                    'key': 'instance_id',
                    'value': 'my_instance',
                },
            ],
        }
        self.job_2 = db_api.job_create(fixture)
        fixture = {
            'id': unit_utils.JOB_UUID3,
            'schedule_id': self.schedule_3['id'],
            'tenant': unit_utils.TENANT3,
            'worker_id': unit_utils.WORKER_UUID2,
            'action': 'snapshot',
            'status': None,
            'timeout': timeout,
            'hard_timeout': hard_timeout,
            'retry_count': 1,
            'job_metadata': [
                {
                    'key': 'instance_id',
                    'value': 'my_instance',
                },
            ],
        }
        self.job_3 = db_api.job_create(fixture)
        fixture = {
            'id': unit_utils.JOB_UUID4,
            'schedule_id': self.schedule_4['id'],
            'tenant': unit_utils.TENANT4,
            'worker_id': unit_utils.WORKER_UUID2,
            'action': 'snapshot',
            'status': None,
            'timeout': timeout,
            'hard_timeout': hard_timeout,
            'retry_count': 1,
            'job_metadata': [
                {
                    'key': 'instance_id',
                    'value': 'my_instance',
                },
            ],
        }
        self.job_4 = db_api.job_create(fixture)

    def test_list(self):
        self.config(limit_param_default=2, api_limit_max=4)
        request = unit_utils.get_fake_request(method='GET')
        workers = self.controller.list(request).get('workers')
        self.assertEqual(len(workers), 2)
        for k in WORKER_ATTRS:
            self.assertEqual(set([s[k] for s in workers]),
                             set([self.worker_1[k], self.worker_2[k]]))

    def test_list_limit(self):
        path = '?limit=2'
        request = unit_utils.get_fake_request(path=path, method='GET')
        workers = self.controller.list(request).get('workers')
        self.assertEqual(len(workers), 2)

    def test_list_limit_max(self):
        self.config(api_limit_max=3)
        path = '?limit=4'
        request = unit_utils.get_fake_request(path=path, method='GET')
        workers = self.controller.list(request).get('workers')
        self.assertEqual(len(workers), 3)

    def test_list_default_limit(self):
        self.config(limit_param_default=2)
        request = unit_utils.get_fake_request(method='GET')
        workers = self.controller.list(request).get('workers')
        self.assertEqual(len(workers), 2)

    def test_list_with_marker(self):
        self.config(limit_param_default=2, api_limit_max=4)
        path = '?marker=%s' % unit_utils.WORKER_UUID1
        request = unit_utils.get_fake_request(path=path, method='GET')
        workers = self.controller.list(request).get('workers')
        self.assertEqual(len(workers), 2)
        for k in WORKER_ATTRS:
            self.assertEqual(set([s[k] for s in workers]),
                             set([self.worker_2[k], self.worker_3[k]]))

    def test_list_marker_not_specified(self):
        self.config(limit_param_default=2, api_limit_max=4)
        path = '?marker=%s' % ''
        request = unit_utils.get_fake_request(path=path, method='GET')
        self.assertRaises(webob.exc.HTTPNotFound,
                          self.controller.list, request)

    def test_list_marker_not_found(self):
        self.config(limit_param_default=2, api_limit_max=4)
        path = '?marker=%s' % '3c5817e2-76cb-41fe-b012-2935e406db87'
        request = unit_utils.get_fake_request(path=path, method='GET')
        self.assertRaises(webob.exc.HTTPNotFound,
                          self.controller.list, request)

    def test_list_invalid_marker(self):
        self.config(limit_param_default=2, api_limit_max=4)
        path = '?marker=%s' % '3c5817e2-76cb'
        request = unit_utils.get_fake_request(path=path, method='GET')
        self.assertRaises(webob.exc.HTTPNotFound,
                          self.controller.list, request)

    def test_list_with_limit_and_marker(self):
        self.config(limit_param_default=2, api_limit_max=4)
        path = '?marker=%s&limit=1' % unit_utils.WORKER_UUID1
        request = unit_utils.get_fake_request(path=path, method='GET')
        workers = self.controller.list(request).get('workers')
        self.assertEqual(len(workers), 1)
        for k in WORKER_ATTRS:
            self.assertEqual(set([s[k] for s in workers]),
                             set([self.worker_2[k]]))

    def test_get(self):
        request = unit_utils.get_fake_request(method='GET')
        actual = self.controller.get(request,
                                     self.worker_1['id']).get('worker')
        for k in WORKER_ATTRS:
            self.assertEqual(actual[k], self.worker_1[k])

    def test_get_not_found(self):
        request = unit_utils.get_fake_request(method='GET')
        worker_id = str(uuid.uuid4())
        self.assertRaises(webob.exc.HTTPNotFound,
                          self.controller.get, request, worker_id)

    def test_create(self):
        request = unit_utils.get_fake_request(method='POST')
        host = 'blah'
        fixture = {'worker': {'host': host, 'id': unit_utils.WORKER_UUID5}}
        actual = self.controller.create(request, fixture)['worker']
        self.assertEqual(host, actual['host'])

    def test_delete(self):
        request = unit_utils.get_fake_request(method='GET')
        request = unit_utils.get_fake_request(method='DELETE')
        self.controller.delete(request, self.worker_1['id'])
        self.assertRaises(exception.NotFound, db_api.worker_get_by_id,
                          self.worker_1['id'])

    def test_delete_not_found(self):
        request = unit_utils.get_fake_request(method='DELETE')
        worker_id = str(uuid.uuid4())
        self.assertRaises(webob.exc.HTTPNotFound,
                          self.controller.delete, request, worker_id)

    def test_get_next_job_unknown_worker_for_action(self):
        request = unit_utils.get_fake_request(method='POST')
        fixture = {'action': 'snapshot'}
        self.assertRaises(webob.exc.HTTPNotFound, self.controller.get_next_job,
                          request, 'unknown_worker_id', fixture)

    def test_get_next_job_none_for_action(self):
        request = unit_utils.get_fake_request(method='POST')
        fixture = {'action': 'dummy'}
        job = self.controller.get_next_job(request,
                                           self.worker_1['id'],
                                           fixture)
        self.assertEqual(job['job'], None)

    def test_get_next_job_for_action(self):
        request = unit_utils.get_fake_request(method='POST')
        fixture = {'action': 'snapshot'}
        job = self.controller.get_next_job(request,
                                           self.worker_1['id'],
                                           fixture)
        self.assertEqual(self.worker_1['id'], job['job']['worker_id'])
