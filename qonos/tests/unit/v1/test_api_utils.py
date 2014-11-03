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

from qonos.api.v1 import api_utils
from qonos.common import exception as exc
from qonos.common import timeutils
from qonos.common import utils
from qonos.tests import utils as test_utils


class TestAPIUtils(test_utils.BaseTestCase):

    def test_check_read_only_properties(self):
        values = {'name': 'instance-1'}
        new_values = api_utils.check_read_only_properties(values)
        self.assertEquals(values, new_values)

    def test_check_read_only_properties_exception(self):
        values = {'name': '1', 'updated_at': '2013-02-02 10:10:23'}
        self.assertRaises(exc.Forbidden,
                          api_utils.check_read_only_properties,
                          values)

    def test_check_read_only_properties_exception_last_scheduled(self):
        values = {'name': '1', 'last_scheduled': '2013-02-02 10:10:23'}
        self.assertRaises(exc.Forbidden,
                          api_utils.check_read_only_properties,
                          values)

    def test_multiple_check_read_only_properties_exception(self):
        values = {
            'name': '1',
            'last_scheduled': '2013-02-02 10:10:23',
            'updated_at': '2013-02-02 10:10:23'
        }
        self.assertRaises(exc.Forbidden,
                          api_utils.check_read_only_properties,
                          values)

    def test_schedule_to_next_run(self):
        timeutils.set_time_override()

        self.called = False

        def fake_next_datetime(min, h, dom, m, dow, start_time):
            self.called = True
            self.assertEqual(min, '*')
            self.assertEqual(h, '*')
            self.assertEqual(dom, '*')
            self.assertEqual(m, '*')
            self.assertEqual(dow, '*')
            self.assertEqual(timeutils.utcnow(), start_time)

        self.stubs.Set(utils,
                       'cron_string_to_next_datetime',
                       fake_next_datetime)

        api_utils.schedule_to_next_run({})
        self.assertTrue(self.called)
        timeutils.clear_time_override()

    def test_schedule_to_next_run_start_time(self):
        expected_start_time = timeutils.utcnow() - datetime.timedelta(2)

        self.called = False

        def fake_next_datetime(min, h, dom, m, dow, start_time):
            self.called = True
            self.assertEqual(min, '*')
            self.assertEqual(h, '*')
            self.assertEqual(dom, '*')
            self.assertEqual(m, '*')
            self.assertEqual(dow, '*')
            self.assertEqual(expected_start_time, start_time)

        self.stubs.Set(utils,
                       'cron_string_to_next_datetime',
                       fake_next_datetime)

        api_utils.schedule_to_next_run({}, expected_start_time)
        self.assertTrue(self.called)
