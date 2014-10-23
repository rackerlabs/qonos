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

from oslo.config import cfg

from qonos.api.v1 import api_utils
from qonos.api.v1 import schedules
from qonos.common import exception
from qonos.common import timeutils
from qonos.common import utils as qonos_utils
from qonos.db.simple import api as db_api
from qonos.tests.unit import utils as unit_utils
from qonos.tests import utils as test_utils


SCHEDULE_ATTRS = ['id', 'tenant', 'action',
                  'minute', 'hour']


CONF = cfg.CONF


class TestSchedulesApi(test_utils.BaseTestCase):

    def setUp(self):
        super(TestSchedulesApi, self).setUp()
        timeutils.set_time_override(datetime.datetime(2013, 2, 17, 2, 0, 0, 0))
        self.controller = schedules.SchedulesController(db_api=db_api)
        self._create_schedules()

    def tearDown(self):
        super(TestSchedulesApi, self).tearDown()
        timeutils.clear_time_override()
        db_api.reset()

    def _create_schedules(self):
        fixture = {
            'id': unit_utils.SCHEDULE_UUID1,
            'tenant': unit_utils.TENANT1,
            'action': 'snapshot',
            'minute': '30',
            'hour': '2',
            'next_run': qonos_utils.cron_string_to_next_datetime(30, 2)
        }
        self.schedule_1 = db_api.schedule_create(fixture)
        fixture = {
            'id': unit_utils.SCHEDULE_UUID2,
            'tenant': unit_utils.TENANT2,
            'action': 'snapshot',
            'minute': '30',
            'hour': '3',
            'next_run': qonos_utils.cron_string_to_next_datetime(30, 3)
        }
        self.schedule_2 = db_api.schedule_create(fixture)
        fixture = {
            'id': unit_utils.SCHEDULE_UUID3,
            'tenant': unit_utils.TENANT3,
            'action': 'snapshot',
            'minute': '30',
            'hour': '4',
            'next_run': qonos_utils.cron_string_to_next_datetime(30, 4)
        }
        self.schedule_3 = db_api.schedule_create(fixture)
        fixture = {
            'id': unit_utils.SCHEDULE_UUID4,
            'tenant': unit_utils.TENANT4,
            'action': 'other',
            'minute': '30',
            'hour': '5',
            'next_run': qonos_utils.cron_string_to_next_datetime(30, 5)
        }
        self.schedule_4 = db_api.schedule_create(fixture)

    def test_list(self):
        request = unit_utils.get_fake_request(method='GET')
        schedules = self.controller.list(request).get('schedules')
        links = self.controller.list(request).get('schedules_links')
        self.assertEqual(len(schedules), 4)
        for k in SCHEDULE_ATTRS:
            self.assertEqual(set([s[k] for s in schedules]),
                             set([self.schedule_1[k], self.schedule_2[k],
                                  self.schedule_3[k], self.schedule_4[k]]))
        for item in links:
            if item.get('rel') == 'next':
                self.assertEqual(item.get('href'), None)

    def test_list_next_run_filtered(self):
        next_run = self.schedule_1['next_run']
        path = '?next_run_after=%s&next_run_before=%s'
        path = path % (next_run, next_run)
        request = unit_utils.get_fake_request(path=path, method='GET')
        schedules = self.controller.list(request).get('schedules')
        self.assertEqual(len(schedules), 1)

    def test_list_next_run_after_filtered(self):
        next_run = self.schedule_1['next_run']
        path = '?next_run_after=%s'
        path = path % next_run
        request = unit_utils.get_fake_request(path=path, method='GET')
        schedules = self.controller.list(request).get('schedules')
        self.assertEqual(len(schedules), 4)

    def test_list_next_run_before_filtered(self):
        next_run = self.schedule_3['next_run']
        path = '?next_run_before=%s'
        path = path % next_run
        request = unit_utils.get_fake_request(path=path, method='GET')
        schedules = self.controller.list(request).get('schedules')
        self.assertEqual(len(schedules), 3)

    def test_list_next_run_filtered_before_less_than_after(self):
        after = self.schedule_3['next_run']
        before = timeutils.isotime(after - datetime.timedelta(seconds=1))
        path = '?next_run_after=%s&next_run_before=%s'
        path = path % (after, before)
        request = unit_utils.get_fake_request(path=path, method='GET')
        schedules = self.controller.list(request).get('schedules')
        self.assertEqual(len(schedules), 0)

    def test_list_limit(self):
        path = '?limit=2'
        request = unit_utils.get_fake_request(path=path, method='GET')
        schedules = self.controller.list(request).get('schedules')
        self.assertEqual(len(schedules), 2)

    def test_list_filter_by_action(self):
        path = '?action=snapshot'
        request = unit_utils.get_fake_request(path=path, method='GET')
        schedules = self.controller.list(request).get('schedules')
        self.assertEqual(len(schedules), 3)

    def test_list_limit_max(self):
        self.config(api_limit_max=3)
        path = '?limit=4'
        request = unit_utils.get_fake_request(path=path, method='GET')
        schedules = self.controller.list(request).get('schedules')
        self.assertEqual(len(schedules), 3)

    def test_list_default_limit(self):
        self.config(limit_param_default=2)
        request = unit_utils.get_fake_request(method='GET')
        schedules = self.controller.list(request).get('schedules')
        self.assertEqual(len(schedules), 2)

    def test_list_with_marker(self):
        self.config(limit_param_default=2, api_limit_max=4)
        path = '?marker=%s' % unit_utils.SCHEDULE_UUID1
        request = unit_utils.get_fake_request(path=path, method='GET')
        schedules = self.controller.list(request).get('schedules')
        self.assertEqual(len(schedules), 2)
        for k in SCHEDULE_ATTRS:
            self.assertEqual(set([s[k] for s in schedules]),
                             set([self.schedule_2[k], self.schedule_3[k]]))

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
        path = '?marker=%s&limit=1' % unit_utils.SCHEDULE_UUID1
        request = unit_utils.get_fake_request(path=path, method='GET')
        schedules = self.controller.list(request).get('schedules')
        self.assertEqual(len(schedules), 1)
        for k in SCHEDULE_ATTRS:
            self.assertEqual(set([s[k] for s in schedules]),
                             set([self.schedule_2[k]]))

    def test_list_schedules_links(self):
        self.config(limit_param_default=2, api_limit_max=4)
        path = '?marker=%s' % unit_utils.SCHEDULE_UUID1
        request = unit_utils.get_fake_request(path=path, method='GET')
        schedules = self.controller.list(request).get('schedules')
        links = self.controller.list(request).get('schedules_links')
        self.assertEqual(len(schedules), 2)
        for k in SCHEDULE_ATTRS:
            self.assertEqual(set([s[k] for s in schedules]),
                             set([self.schedule_2[k], self.schedule_3[k]]))
        for item in links:
            if item.get('rel') == 'next':
                marker = unit_utils.SCHEDULE_UUID3
                self.assertEqual(item.get('href'), '/v1/schedules?marker=%s' %
                                 marker)

    def test_get(self):
        request = unit_utils.get_fake_request(method='GET')
        actual = self.controller.get(request,
                                     self.schedule_1['id']).get('schedule')
        for k in SCHEDULE_ATTRS:
            self.assertEqual(actual[k], self.schedule_1[k])

    def test_get_not_found(self):
        request = unit_utils.get_fake_request(method='GET')
        schedule_id = str(uuid.uuid4())
        self.assertRaises(webob.exc.HTTPNotFound,
                          self.controller.get, request, schedule_id)

    def test_create(self):
        fixture = {'schedule': {
            'id': unit_utils.SCHEDULE_UUID5,
            'tenant': unit_utils.TENANT1,
            'action': 'snapshot',
            'minute': 30,
            'hour': 2,
        }}
        expected = fixture['schedule']
        request = unit_utils.get_fake_request(method='POST')

        actual = self.controller.create(request, fixture)['schedule']

        self.assertNotEqual(actual.get('id'), None)
        self.assertNotEqual(actual.get('created_at'), None)
        self.assertNotEqual(actual.get('updated_at'), None)
        self.assertNotEqual(actual.get('next_run'), None)
        self.assertEqual(expected['tenant'], actual['tenant'])
        self.assertEqual(expected['action'], actual['action'])
        self.assertEqual(expected['minute'], actual['minute'])
        self.assertEqual(expected['hour'], actual['hour'])

    def test_create_zero_hour(self):
        hour = 0
        fixture = {'schedule': {
            'id': unit_utils.SCHEDULE_UUID5,
            'tenant': unit_utils.TENANT1,
            'action': 'snapshot',
            'minute': 30,
            'hour': hour,
        }}
        expected = fixture['schedule']
        request = unit_utils.get_fake_request(method='POST')

        actual = self.controller.create(request, fixture)['schedule']

        self.assertNotEqual(actual.get('id'), None)
        self.assertNotEqual(actual.get('created_at'), None)
        self.assertNotEqual(actual.get('updated_at'), None)
        now = timeutils.utcnow()
        if not (now.hour == hour and now.minute < 30):
            now = now + datetime.timedelta(days=1)
        expected_next_run = timeutils.isotime(
            now.replace(hour=hour, minute=30, second=0,
                        microsecond=0))
        self.assertEqual(expected_next_run, actual['next_run'])
        self.assertEqual(expected['tenant'], actual['tenant'])
        self.assertEqual(expected['action'], actual['action'])
        self.assertEqual(expected['minute'], actual['minute'])
        self.assertEqual(expected['hour'], actual['hour'])

    def test_create_no_body_bad_request(self):
        request = unit_utils.get_fake_request(method='POST')
        self.assertRaises(webob.exc.HTTPBadRequest, self.controller.create,
                          request, None)

    def test_create_malformed_body_bad_request(self):
        request = unit_utils.get_fake_request(method='POST')
        self.assertRaises(webob.exc.HTTPBadRequest, self.controller.create,
                          request, 'fake-body')

    def test_create_no_schedule_bad_request(self):
        request = unit_utils.get_fake_request(method='POST')
        self.assertRaises(webob.exc.HTTPBadRequest, self.controller.create,
                          request, {'minute': '5'})

    def test_create_blank_tenant(self):
        fixture = {'schedule': {
            'id': unit_utils.SCHEDULE_UUID5,
            'tenant': '',
            'action': 'snapshot',
            'minute': 30,
            'hour': 2,
        }}

        self.assertRaises(webob.exc.HTTPBadRequest, self.controller.create,
                          fixture)

    def test_create_no_tenant(self):
        fixture = {'schedule': {
            'id': unit_utils.SCHEDULE_UUID5,
            'action': 'snapshot',
            'minute': 30,
            'hour': 2,
        }}

        self.assertRaises(webob.exc.HTTPBadRequest, self.controller.create,
                          fixture)

    def test_create_blank_action(self):
        fixture = {'schedule': {
            'id': unit_utils.SCHEDULE_UUID5,
            'action': '',
            'minute': 30,
            'hour': 2,
        }}

        self.assertRaises(webob.exc.HTTPBadRequest, self.controller.create,
                          fixture)

    def test_create_no_action(self):
        fixture = {'schedule': {
            'id': unit_utils.SCHEDULE_UUID5,
            'minute': 30,
            'hour': 2,
        }}

        self.assertRaises(webob.exc.HTTPBadRequest, self.controller.create,
                          fixture)

    def test_delete(self):
        request = unit_utils.get_fake_request(method='GET')
        request = unit_utils.get_fake_request(method='DELETE')
        self.controller.delete(request, self.schedule_1['id'])
        self.assertRaises(exception.NotFound, db_api.worker_get_by_id,
                          self.schedule_1['id'])

    def test_delete_not_found(self):
        request = unit_utils.get_fake_request(method='DELETE')
        schedule_id = str(uuid.uuid4())
        self.assertRaises(webob.exc.HTTPNotFound,
                          self.controller.delete, request, schedule_id)

    def test_update(self):

        expected_next_run = '1989-01-19T12:00:00Z'

        def fake_schedule_to_next_run(*args, **kwargs):
            return timeutils.parse_isotime(expected_next_run)

        self.stubs.Set(api_utils, 'schedule_to_next_run',
                       fake_schedule_to_next_run)

        request = unit_utils.get_fake_request(method='PUT')
        update_fixture = {'schedule':
                          {'minute': '55',
                           'hour': '5',
                           'day': '2',
                           'day_of_week': '4',
                           'day_of_month': '23',
                           'action': 'new-action',
                           'tenant': 'new-tenant',
                           }}

        updated = self.controller.update(request, self.schedule_1['id'],
                                         update_fixture)['schedule']

        self.assertEqual(update_fixture['schedule']['minute'],
                         updated['minute'])
        self.assertEqual(update_fixture['schedule']['hour'],
                         updated['hour'])
        self.assertEqual(update_fixture['schedule']['day'],
                         updated['day'])
        self.assertEqual(update_fixture['schedule']['day_of_week'],
                         updated['day_of_week'])
        self.assertEqual(update_fixture['schedule']['day_of_month'],
                         updated['day_of_month'])
        self.assertEqual(update_fixture['schedule']['action'],
                         updated['action'])
        self.assertEqual(update_fixture['schedule']['tenant'],
                         updated['tenant'])
        self.assertEqual(updated['next_run'], expected_next_run)

    def test_update_invalid_next_run(self):
        request = unit_utils.get_fake_request(method='PUT')
        update_fixture = {'schedule': {
                          'next_run': '12345'
                          }}

        self.assertRaises(webob.exc.HTTPBadRequest, self.controller.update,
                          request, self.schedule_1['id'], update_fixture)

    def test_update_valid_next_run(self):
        request = unit_utils.get_fake_request(method='PUT')
        expected_next_run = '1989-01-19T12:00:00Z'
        update_fixture = {'schedule': {
                          'next_run': expected_next_run
                          }}

        updated = self.controller.update(request, self.schedule_1['id'],
                                         update_fixture)['schedule']

        self.assertEqual(updated['next_run'], expected_next_run)

    def test_update_with_hour(self):

        expected_next_run = '1989-01-19T12:00:00Z'

        def fake_schedule_to_next_run(*args, **kwargs):
            return timeutils.parse_isotime(expected_next_run)

        self.stubs.Set(api_utils, 'schedule_to_next_run',
                       fake_schedule_to_next_run)

        request = unit_utils.get_fake_request(method='PUT')
        update_fixture = {'schedule': {'hour': '5'}}

        updated = self.controller.update(request, self.schedule_1['id'],
                                         update_fixture)['schedule']

        self.assertNotEqual(updated.get('created_at'), None)
        self.assertNotEqual(updated.get('updated_at'), None)
        self.assertEqual(self.schedule_1['tenant'], updated['tenant'])
        self.assertEqual(self.schedule_1['action'], updated['action'])
        self.assertEqual(update_fixture['schedule']['hour'],
                         updated['hour'])
        self.assertFalse(updated['minute'])
        self.assertFalse(updated['month'])
        self.assertFalse(updated['day_of_week'])
        self.assertFalse(updated['day_of_month'])
        self.assertEqual(updated['next_run'], expected_next_run)

    def test_update_with_minute(self):

        expected_next_run = '1989-01-19T12:00:00Z'

        def fake_schedule_to_next_run(*args, **kwargs):
            return timeutils.parse_isotime(expected_next_run)

        self.stubs.Set(api_utils, 'schedule_to_next_run',
                       fake_schedule_to_next_run)

        request = unit_utils.get_fake_request(method='PUT')
        update_fixture = {'schedule': {'minute': '5'}}

        updated = self.controller.update(request, self.schedule_1['id'],
                                         update_fixture)['schedule']

        self.assertNotEqual(updated.get('created_at'), None)
        self.assertNotEqual(updated.get('updated_at'), None)
        self.assertEqual(self.schedule_1['tenant'], updated['tenant'])
        self.assertEqual(self.schedule_1['action'], updated['action'])
        self.assertFalse(updated['hour'])
        self.assertFalse(updated['month'])
        self.assertFalse(updated['day_of_week'])
        self.assertFalse(updated['day_of_month'])
        self.assertEqual(update_fixture['schedule']['minute'],
                         updated['minute'])
        self.assertEqual(updated['next_run'], expected_next_run)

    def test_update_with_month(self):

        expected_next_run = '1989-01-19T12:00:00Z'

        def fake_schedule_to_next_run(*args, **kwargs):
            return timeutils.parse_isotime(expected_next_run)

        self.stubs.Set(api_utils, 'schedule_to_next_run',
                       fake_schedule_to_next_run)

        request = unit_utils.get_fake_request(method='PUT')
        update_fixture = {'schedule': {'month': '5'}}

        updated = self.controller.update(request, self.schedule_1['id'],
                                         update_fixture)['schedule']

        self.assertNotEqual(updated.get('created_at'), None)
        self.assertNotEqual(updated.get('updated_at'), None)
        self.assertEqual(self.schedule_1['tenant'], updated['tenant'])
        self.assertEqual(self.schedule_1['action'], updated['action'])
        self.assertEqual(update_fixture['schedule']['month'],
                         updated['month'])
        self.assertFalse(updated['minute'])
        self.assertFalse(updated['hour'])
        self.assertFalse(updated['day_of_week'])
        self.assertFalse(updated['day_of_month'])
        self.assertEqual(updated['next_run'], expected_next_run)

    def test_update_with_day_of_week(self):

        expected_next_run = '1989-01-19T12:00:00Z'

        def fake_schedule_to_next_run(*args, **kwargs):
            return timeutils.parse_isotime(expected_next_run)

        self.stubs.Set(api_utils, 'schedule_to_next_run',
                       fake_schedule_to_next_run)

        request = unit_utils.get_fake_request(method='PUT')
        update_fixture = {'schedule': {'day_of_week': '5'}}

        updated = self.controller.update(request, self.schedule_1['id'],
                                         update_fixture)['schedule']

        self.assertNotEqual(updated.get('created_at'), None)
        self.assertNotEqual(updated.get('updated_at'), None)
        self.assertEqual(self.schedule_1['tenant'], updated['tenant'])
        self.assertEqual(self.schedule_1['action'], updated['action'])
        self.assertEqual(update_fixture['schedule']['day_of_week'],
                         updated['day_of_week'])
        self.assertFalse(updated['minute'])
        self.assertFalse(updated['hour'])
        self.assertFalse(updated['month'])
        self.assertFalse(updated['day_of_month'])
        self.assertEqual(updated['next_run'], expected_next_run)

    def test_update_with_day_of_month(self):

        expected_next_run = '1989-01-19T12:00:00Z'

        def fake_schedule_to_next_run(*args, **kwargs):
            return timeutils.parse_isotime(expected_next_run)

        self.stubs.Set(api_utils, 'schedule_to_next_run',
                       fake_schedule_to_next_run)

        request = unit_utils.get_fake_request(method='PUT')
        update_fixture = {'schedule': {'day_of_month': '5'}}

        updated = self.controller.update(request, self.schedule_1['id'],
                                         update_fixture)['schedule']

        self.assertNotEqual(updated.get('created_at'), None)
        self.assertNotEqual(updated.get('updated_at'), None)
        self.assertEqual(self.schedule_1['tenant'], updated['tenant'])
        self.assertEqual(self.schedule_1['action'], updated['action'])
        self.assertEqual(update_fixture['schedule']['day_of_month'],
                         updated['day_of_month'])
        self.assertFalse(updated['minute'])
        self.assertFalse(updated['hour'])
        self.assertFalse(updated['month'])
        self.assertFalse(updated['day_of_week'])
        self.assertEqual(updated['next_run'], expected_next_run)

    def test_update_tenant(self):

        new_tenant = 'new-tenant-name'

        def fake_schedule_to_next_run(*args, **kwargs):
            self.fail('next_run should not be updated')

        self.stubs.Set(api_utils, 'schedule_to_next_run',
                       fake_schedule_to_next_run)

        request = unit_utils.get_fake_request(method='PUT')
        update_fixture = {'schedule': {'tenant': new_tenant}}

        updated = self.controller.update(request, self.schedule_1['id'],
                                         update_fixture)['schedule']

        self.assertNotEqual(updated.get('created_at'), None)
        self.assertNotEqual(updated.get('updated_at'), None)
        self.assertEqual(new_tenant, updated['tenant'])
        self.assertEqual(self.schedule_1['action'], updated['action'])
        self.assertEqual(self.schedule_1['minute'], updated['minute'])
        self.assertEqual(updated['next_run'],
                         timeutils.isotime(self.schedule_1['next_run']))

    def test_update_blank_tenant(self):
        request = unit_utils.get_fake_request(method='PUT')
        schedule_id = self.schedule_1['id']
        update_fixture = {'schedule': {'tenant': ''}}

        self.assertRaises(webob.exc.HTTPBadRequest, self.controller.update,
                          request, schedule_id, update_fixture)

    def test_update_whitespace_tenant(self):
        request = unit_utils.get_fake_request(method='PUT')
        schedule_id = self.schedule_1['id']
        update_fixture = {'schedule': {'tenant': '   '}}

        self.assertRaises(webob.exc.HTTPBadRequest, self.controller.update,
                          request, schedule_id, update_fixture)

    def test_update_no_tenant(self):
        request = unit_utils.get_fake_request(method='PUT')
        update_fixture = {'schedule': {'action': 'snapshot'}}
        old_tenant = self.schedule_1['tenant']

        updated = self.controller.update(request, self.schedule_1['id'],
                                         update_fixture)['schedule']

        self.assertEqual(updated.get('tenant'), old_tenant)

    def test_update_ignore_read_only(self):
        request = unit_utils.get_fake_request(method='PUT')
        schedule_id = self.schedule_1['id']
        schedule = {'schedule': {'updated_at': '2013-01-02 20:20:20'}}
        self.assertRaises(webob.exc.HTTPForbidden, self.controller.update,
                          request, schedule_id, schedule)

    def test_update_not_found(self):
        request = unit_utils.get_fake_request(method='PUT')
        schedule_id = str(uuid.uuid4())
        self.assertRaises(webob.exc.HTTPNotFound, self.controller.update,
                          request, schedule_id, {'schedule': {}})

    def test_update_no_body_bad_request(self):
        request = unit_utils.get_fake_request(method='PUT')
        schedule_id = str(uuid.uuid4())
        self.assertRaises(webob.exc.HTTPBadRequest, self.controller.update,
                          request, schedule_id, None)

    def test_update_no_schedule_bad_request(self):
        request = unit_utils.get_fake_request(method='PUT')
        schedule_id = str(uuid.uuid4())
        self.assertRaises(webob.exc.HTTPBadRequest, self.controller.update,
                          request, schedule_id, {'minute': '5'})
