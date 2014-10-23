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

from qonos.api.v1 import api_utils
from qonos.api.v1 import jobs
from qonos.common import exception
from qonos.common import timeutils
from qonos.common import utils
import qonos.db.simple.api as db_api
from qonos.tests.unit import utils as unit_utils
from qonos.tests import utils as test_utils


JOB_ATTRS = ['id', 'schedule_id', 'worker_id', 'retry_count', 'status']


class TestJobsApi(test_utils.BaseTestCase):

    def setUp(self):
        super(TestJobsApi, self).setUp()
        timeutils.set_time_override()
        self.controller = jobs.JobsController(db_api=db_api)
        self._create_jobs()

    def tearDown(self):
        super(TestJobsApi, self).tearDown()
        timeutils.clear_time_override()
        db_api.reset()

    def _stub_notifications(self, ex_context, ex_event_type, ex_payload,
                            ex_level):
        def fake_gen_notify(context, event_type, payload, level='INFO'):
            self.assertEqual(ex_context, context)
            self.assertEqual(ex_event_type, event_type)
            # NOTE(isethi): Avoiding repetitive checking of job
            self.assertTrue(payload['job'] is not None)
            self.assertEqual(ex_level, level)
        self.stubs.Set(utils, 'generate_notification', fake_gen_notify)

    def _create_jobs(self):
        next_run = timeutils.parse_isotime(
            '2012-11-27T02:30:00Z').replace(tzinfo=None)
        fixture = {
            'id': unit_utils.SCHEDULE_UUID1,
            'tenant': unit_utils.TENANT1,
            'action': 'snapshot',
            'minute': '30',
            'hour': '2',
            'next_run': next_run,
        }
        self.schedule_1 = db_api.schedule_create(fixture)
        fixture = {
            'id': unit_utils.SCHEDULE_UUID2,
            'tenant': unit_utils.TENANT2,
            'action': 'snapshot',
            'minute': '30',
            'hour': '2',
            'next_run': next_run,
            'schedule_metadata': [{'key': 'instance_id',
                                   'value': 'my_instance',
                                   }
                                  ],
        }
        self.schedule_2 = db_api.schedule_create(fixture)

        now = timeutils.utcnow()
        timeout = now + datetime.timedelta(hours=1)
        hard_timeout = now + datetime.timedelta(hours=8)

        fixture = {
            'id': unit_utils.JOB_UUID1,
            'schedule_id': self.schedule_1['id'],
            'tenant': unit_utils.TENANT1,
            'worker_id': unit_utils.WORKER_UUID1,
            'action': 'snapshot',
            'status': 'QUEUED',
            'timeout': timeout,
            'hard_timeout': hard_timeout,
            'retry_count': 0,
        }
        self.job_1 = db_api.job_create(fixture)
        timeout = now + datetime.timedelta(hours=2)
        hard_timeout = now + datetime.timedelta(hours=4)
        fixture = {
            'id': unit_utils.JOB_UUID2,
            'schedule_id': self.schedule_2['id'],
            'tenant': unit_utils.TENANT2,
            'worker_id': unit_utils.WORKER_UUID2,
            'action': 'snapshot',
            'status': 'ERROR',
            'timeout': timeout,
            'hard_timeout': hard_timeout,
            'retry_count': 1,
            'job_metadata': [{'key': 'instance_id',
                              'value': 'my_instance',
                              },
                             ]
        }
        self.job_2 = db_api.job_create(fixture)
        fixture = {
            'id': unit_utils.JOB_UUID3,
            'schedule_id': self.schedule_1['id'],
            'tenant': unit_utils.TENANT3,
            'worker_id': unit_utils.WORKER_UUID1,
            'action': 'snapshot',
            'status': 'QUEUED',
            'timeout': timeout,
            'hard_timeout': hard_timeout,
            'retry_count': 0,
        }
        self.job_3 = db_api.job_create(fixture)
        fixture = {
            'id': unit_utils.JOB_UUID4,
            'schedule_id': self.schedule_1['id'],
            'tenant': unit_utils.TENANT1,
            'worker_id': unit_utils.WORKER_UUID1,
            'action': 'test_action',
            'status': 'QUEUED',
            'timeout': timeout,
            'hard_timeout': hard_timeout,
            'retry_count': 0,
        }
        self.job_4 = db_api.job_create(fixture)

    def test_list(self):
        self.config(api_limit_max=4, limit_param_default=2)
        request = unit_utils.get_fake_request(method='GET')
        response = self.controller.list(request)
        jobs = response.get('jobs')
        links = response.get('jobs_links')
        self.assertEqual(len(jobs), 2)
        for k in JOB_ATTRS:
            self.assertEqual(set([s[k] for s in jobs]),
                             set([self.job_1[k], self.job_2[k]]))

        self.assertTrue(links)
        for item in links:
            if item.get('rel') == 'next':
                marker = self.job_2['id']
                self.assertEqual(item.get('href'),
                                 '/v1/jobs?marker=%s' % marker)

    def test_list_limit(self):
        path = '?limit=2'
        request = unit_utils.get_fake_request(path=path, method='GET')
        jobs = self.controller.list(request).get('jobs')
        self.assertEqual(len(jobs), 2)

    def test_list_limit_max(self):
        self.config(api_limit_max=3)
        path = '?limit=4'
        request = unit_utils.get_fake_request(path=path, method='GET')
        jobs = self.controller.list(request).get('jobs')
        self.assertEqual(len(jobs), 3)

    def test_list_default_limit(self):
        self.config(limit_param_default=2)
        request = unit_utils.get_fake_request(method='GET')
        jobs = self.controller.list(request).get('jobs')
        self.assertEqual(len(jobs), 2)

    def test_list_with_marker(self):
        self.config(limit_param_default=2, api_limit_max=4)
        path = '?marker=%s' % unit_utils.JOB_UUID1
        request = unit_utils.get_fake_request(path=path, method='GET')
        jobs = self.controller.list(request).get('jobs')
        self.assertEqual(len(jobs), 2)
        for k in JOB_ATTRS:
            self.assertEqual(set([s[k] for s in jobs]),
                             set([self.job_2[k], self.job_3[k]]))

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
        path = '?marker=%s&limit=1' % unit_utils.JOB_UUID1
        request = unit_utils.get_fake_request(path=path, method='GET')
        jobs = self.controller.list(request).get('jobs')
        self.assertEqual(len(jobs), 1)
        for k in JOB_ATTRS:
            self.assertEqual(set([s[k] for s in jobs]),
                             set([self.job_2[k]]))

    def test_list_jobs_links(self):
        self.config(limit_param_default=2, api_limit_max=4)
        path = '?marker=%s' % unit_utils.JOB_UUID1
        request = unit_utils.get_fake_request(path=path, method='GET')
        response = self.controller.list(request)
        jobs = response.get('jobs')
        links = response.get('jobs_links')
        self.assertEqual(len(jobs), 2)
        for k in JOB_ATTRS:
            self.assertEqual(set([s[k] for s in jobs]),
                             set([self.job_2[k], self.job_3[k]]))
        for item in links:
            if item.get('rel') == 'next':
                marker = unit_utils.JOB_UUID3
                self.assertEqual(item.get('href'), '/v1/jobs?marker=%s' %
                                 marker)

    def test_list_with_schedule_id_filter(self):
        path = '?schedule_id=%s' % unit_utils.SCHEDULE_UUID1
        request = unit_utils.get_fake_request(path=path, method='GET')
        jobs = self.controller.list(request).get('jobs')
        self.assertEqual(len(jobs), 3)

    def test_list_with_tenant_filter(self):
        path = '?tenant=%s' % unit_utils.TENANT3
        request = unit_utils.get_fake_request(path=path, method='GET')
        jobs = self.controller.list(request).get('jobs')
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]['id'], self.job_3['id'])

    def test_list_with_action_filter(self):
        path = '?action=%s' % 'test_action'

        request = unit_utils.get_fake_request(path=path, method='GET')
        jobs = self.controller.list(request).get('jobs')
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]['id'], self.job_4['id'])

    def test_list_with_worker_id_filter(self):
        path = '?worker_id=%s' % unit_utils.WORKER_UUID2

        request = unit_utils.get_fake_request(path=path, method='GET')
        jobs = self.controller.list(request).get('jobs')
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]['id'], self.job_2['id'])

    def test_list_with_status_filter(self):
        path = '?status=ERROR'

        request = unit_utils.get_fake_request(path=path, method='GET')
        jobs = self.controller.list(request).get('jobs')
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]['id'], self.job_2['id'])

    def test_list_with_status_filter_case_insensitive(self):
        path = '?status=Error'

        request = unit_utils.get_fake_request(path=path, method='GET')
        jobs = self.controller.list(request).get('jobs')
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]['id'], self.job_2['id'])

    def test_list_with_timeout_filter(self):
        timeout = timeutils.isotime(self.job_1['timeout'])
        path = '?timeout=%s' % timeout

        request = unit_utils.get_fake_request(path=path, method='GET')
        jobs = self.controller.list(request).get('jobs')
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]['id'], self.job_1['id'])

    def test_list_with_hard_timeout_filter(self):
        hard_timeout = timeutils.isotime(self.job_1['hard_timeout'])
        path = '?hard_timeout=%s' % hard_timeout

        request = unit_utils.get_fake_request(path=path, method='GET')
        jobs = self.controller.list(request).get('jobs')
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]['id'], self.job_1['id'])

    def test_create(self):

        expected_next_run = timeutils.parse_isotime(
            '1989-01-19T12:00:00Z').replace(tzinfo=None)
        self._stub_notifications(None, 'qonos.job.create', 'fake-payload',
                                 'INFO')

        def fake_schedule_to_next_run(_schedule, start_time=None):
            self.assertEqual(timeutils.utcnow(), start_time)
            return expected_next_run

        self.stubs.Set(api_utils, 'schedule_to_next_run',
                       fake_schedule_to_next_run)

        request = unit_utils.get_fake_request(method='POST')
        fixture = {'job': {'schedule_id': self.schedule_1['id']}}
        job = self.controller.create(request, fixture).get('job')
        self.assertNotEqual(job, None)
        self.assertNotEqual(job.get('id'), None)
        self.assertEqual(job['schedule_id'], self.schedule_1['id'])
        self.assertEqual(job['tenant'], self.schedule_1['tenant'])
        self.assertEqual(job['action'], self.schedule_1['action'])
        self.assertEqual(job['status'], 'QUEUED')
        self.assertEqual(len(job['metadata']), 0)

        schedule = db_api.schedule_get_by_id(self.schedule_1['id'])
        self.assertNotEqual(schedule['next_run'], self.schedule_1['next_run'])
        self.assertEqual(schedule['next_run'], expected_next_run)
        self.assertNotEqual(schedule['last_scheduled'],
                            self.schedule_1.get('last_scheduled'))
        self.assertTrue(schedule.get('last_scheduled'))

    def test_create_with_next_run(self):

        expected_next_run = timeutils.parse_isotime(
            '1989-01-19T12:00:00Z').replace(tzinfo=None)

        def fake_schedule_to_next_run(_schedule, start_time=None):
            self.assertEqual(timeutils.utcnow(), start_time)
            return expected_next_run

        self.stubs.Set(api_utils, 'schedule_to_next_run',
                       fake_schedule_to_next_run)

        self._stub_notifications(None, 'qonos.job.create', 'fake-payload',
                                 'INFO')
        request = unit_utils.get_fake_request(method='POST')
        fixture = {'job': {'schedule_id': self.schedule_1['id'],
                           'next_run':
                           timeutils.isotime(self.schedule_1['next_run'])}}
        job = self.controller.create(request, fixture).get('job')
        self.assertNotEqual(job, None)
        self.assertNotEqual(job.get('id'), None)
        self.assertEqual(job['schedule_id'], self.schedule_1['id'])
        self.assertEqual(job['tenant'], self.schedule_1['tenant'])
        self.assertEqual(job['action'], self.schedule_1['action'])
        self.assertEqual(job['status'], 'QUEUED')
        self.assertEqual(len(job['metadata']), 0)

        schedule = db_api.schedule_get_by_id(self.schedule_1['id'])
        self.assertNotEqual(schedule['next_run'], self.schedule_1['next_run'])
        self.assertEqual(schedule['next_run'], expected_next_run)
        self.assertNotEqual(schedule['last_scheduled'],
                            self.schedule_1.get('last_scheduled'))
        self.assertTrue(schedule.get('last_scheduled'))

    def test_create_next_run_differs(self):

        expected_next_run = '1989-01-19T12:00:00Z'

        self._stub_notifications(None, 'qonos.job.create', 'fake-payload',
                                 'INFO')
        request = unit_utils.get_fake_request(method='POST')
        fixture = {'job': {'schedule_id': self.schedule_1['id'],
                           'next_run': expected_next_run}}
        self.assertRaises(webob.exc.HTTPConflict,
                          self.controller.create, request, fixture)

    def test_create_next_run_invalid_format(self):
        expected_next_run = '12345'
        self._stub_notifications(None, 'qonos.job.create', 'fake-payload',
                                 'INFO')
        request = unit_utils.get_fake_request(method='POST')
        fixture = {'job': {'schedule_id': self.schedule_1['id'],
                           'next_run': expected_next_run}}
        self.assertRaises(webob.exc.HTTPBadRequest,
                          self.controller.create, request, fixture)

    def test_create_with_metadata(self):
        self._stub_notifications(None, 'qonos.job.create', 'fake-payload',
                                 'INFO')
        request = unit_utils.get_fake_request(method='POST')
        fixture = {'job': {'schedule_id': self.schedule_2['id']}}
        job = self.controller.create(request, fixture).get('job')
        self.assertNotEqual(job, None)
        self.assertNotEqual(job.get('id'), None)
        self.assertEqual(job['schedule_id'], self.schedule_2['id'])
        self.assertEqual(job['tenant'], self.schedule_2['tenant'])
        self.assertEqual(job['action'], self.schedule_2['action'])
        self.assertEqual(job['status'], 'QUEUED')
        self.assertEqual(len(job['metadata']), 1)
        self.assertTrue('instance_id' in job['metadata'])
        self.assertEqual(job['metadata']['instance_id'], 'my_instance')

    def test_get(self):
        request = unit_utils.get_fake_request(method='GET')
        job = self.controller.get(request, self.job_1['id']).get('job')
        self.assertEqual(job['status'], 'QUEUED')
        self.assertEqual(job['schedule_id'], self.schedule_1['id'])
        self.assertEqual(job['worker_id'], unit_utils.WORKER_UUID1)
        self.assertEqual(job['retry_count'], 0)
        self.assertNotEqual(job['updated_at'], None)
        self.assertNotEqual(job['created_at'], None)

    def test_get_with_metadata(self):
        request = unit_utils.get_fake_request(method='GET')
        job = self.controller.get(request, self.job_2['id']).get('job')
        self.assertEqual(job['status'], 'ERROR')
        self.assertEqual(job['schedule_id'], self.schedule_2['id'])
        self.assertEqual(job['worker_id'], unit_utils.WORKER_UUID2)
        self.assertEqual(job['retry_count'], 1)
        self.assertNotEqual(job['updated_at'], None)
        self.assertNotEqual(job['created_at'], None)
        self.assertEqual(len(job['metadata']), 1)
        self.assertTrue('instance_id' in job['metadata'])
        self.assertEqual(job['metadata']['instance_id'], 'my_instance')

    def test_get_not_found(self):
        request = unit_utils.get_fake_request(method='GET')
        self.assertRaises(webob.exc.HTTPNotFound, self.controller.get,
                          request, uuid.uuid4())

    def test_delete(self):
        request = unit_utils.get_fake_request(method='DELETE')
        self.controller.delete(request, self.job_1['id'])
        self.assertRaises(exception.NotFound, db_api.job_get_by_id,
                          self.job_1['id'])

    def test_delete_not_found(self):
        request = unit_utils.get_fake_request(method='DELETE')
        job_id = str(uuid.uuid4())
        self.assertRaises(webob.exc.HTTPNotFound,
                          self.controller.delete, request, job_id)

    def test_update_status(self):
        timeout = datetime.datetime(2012, 11, 16, 22, 0)
        request = unit_utils.get_fake_request(method='PUT')
        body = {'status': {'status': 'PROCESSING',
                           'timeout': str(timeout)
                           }}
        job_status = self.controller.update_status(request,
                                                   self.job_1['id'],
                                                   body)['status']
        actual_status = job_status['status']
        actual_timeout = job_status['timeout']
        self.assertEqual(actual_status, body['status']['status'])
        self.assertEqual(actual_timeout, timeout)

    def test_update_status_without_timeout(self):
        request = unit_utils.get_fake_request(method='PUT')
        body = {'status': {'status': 'DONE'}}
        actual = self.controller.update_status(request,
                                               self.job_1['id'],
                                               body)['status']
        self.assertEqual(actual['status'], body['status']['status'])

    def test_update_status_uppercases_status(self):
        request = unit_utils.get_fake_request(method='PUT')
        body = {'status': {'status': 'done'}}
        self.controller.update_status(request, self.job_1['id'], body)
        actual = db_api.job_get_by_id(self.job_1['id'])['status']
        self.assertEqual(actual, body['status']['status'].upper())

    def test_update_status_empty_body(self):
        request = unit_utils.get_fake_request(method='PUT')
        body = {}
        self.assertRaises(webob.exc.HTTPBadRequest,
                          self.controller.update_status,
                          request, unit_utils.JOB_UUID1, body)

    def test_update_status_job_not_found(self):
        request = unit_utils.get_fake_request(method='PUT')
        job_id = str(uuid.uuid4())
        body = {'status': {'status': 'QUEUED'}}
        self.assertRaises(webob.exc.HTTPNotFound,
                          self.controller.update_status,
                          request, job_id, body)
