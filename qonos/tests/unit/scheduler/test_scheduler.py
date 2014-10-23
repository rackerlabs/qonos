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

import mox
import time

from qonos.common import timeutils
from qonos.qonosclient import exception as client_exc
from qonos.scheduler import scheduler
from qonos.tests.unit import utils as unit_utils
from qonos.tests import utils as test_utils


class TestScheduler(test_utils.BaseTestCase):

    def setUp(self):
        super(TestScheduler, self).setUp()
        self.mox = mox.Mox()
        self.client = self.mox.CreateMockAnything()

        def client_factory(*args, **kwargs):
            return self.client

        self.scheduler = scheduler.Scheduler(client_factory)

    def tearDown(self):
        super(TestScheduler, self).tearDown()

    def test_run_loop(self):
        self.config(job_schedule_interval=5, group='scheduler')
        timeutils.set_time_override()
        current_time = timeutils.isotime()
        called = {'enqueue_jobs': False}

        def fake(end_time=None):  # assert only end_time kwarg is passed
            self.assertEqual(end_time, current_time)
            called['enqueue_jobs'] = True

        self.stubs.Set(self.scheduler, 'enqueue_jobs', fake)
        fake_sleep = lambda x: None
        self.stubs.Set(time, 'sleep', fake_sleep)

        self.scheduler.run(run_once=True)
        self.assertTrue(called['enqueue_jobs'])

    def test_run_loop_take_too_long(self):
        self.config(job_schedule_interval=-1, group='scheduler')
        called = {'enqueue_jobs': False,
                  'log_warn': False}

        def fake(*args, **kwargs):
            called['enqueue_jobs'] = True

        self.stubs.Set(self.scheduler, 'enqueue_jobs', fake)
        fake_sleep = lambda x: None
        self.stubs.Set(time, 'sleep', fake_sleep)

        def fake_warn(msg, *args, **kwargs):
            called['log_warn'] = True

        self.stubs.Set(scheduler.LOG, 'warn', fake_warn)

        self.scheduler.run(run_once=True)
        self.assertTrue(called['enqueue_jobs'])
        self.assertTrue(called['log_warn'])

    def test_enqueue_jobs(self):
        called = {'get_schedules': False}
        next_run = '2010-11-30T17:00:00Z'

        def fake(*args, **kwargs):
            called['get_schedules'] = True
            return [{'id': unit_utils.SCHEDULE_UUID1, 'next_run': next_run}]

        self.stubs.Set(self.scheduler, 'get_schedules', fake)
        self.client.create_job(unit_utils.SCHEDULE_UUID1, next_run)
        self.mox.ReplayAll()
        self.scheduler.enqueue_jobs()
        self.mox.VerifyAll()

    def test_enqueue_jobs_job_exists(self):
        called = {'get_schedules': False}
        next_run = '2010-11-30T17:00:00Z'

        def fake(*args, **kwargs):
            called['get_schedules'] = True
            return [{'id': unit_utils.SCHEDULE_UUID1, 'next_run': next_run}]

        self.stubs.Set(self.scheduler, 'get_schedules', fake)
        self.client.create_job(
            unit_utils.SCHEDULE_UUID1,
            next_run).AndRaise(client_exc.Duplicate())
        self.mox.ReplayAll()
        self.scheduler.enqueue_jobs()
        self.mox.VerifyAll()

    def test_get_schedules(self):
        timeutils.set_time_override()
        start_time = timeutils.isotime()
        timeutils.advance_time_seconds(30)
        end_time = timeutils.isotime()

        filter_args = {'next_run_after': start_time,
                       'next_run_before': end_time}
        self.client.list_schedules(filter_args=filter_args).AndReturn([])
        self.mox.ReplayAll()
        self.scheduler.get_schedules(start_time, end_time)
        self.mox.VerifyAll()

    def test_get_schedules_no_previous_run(self):
        end_time = timeutils.isotime()

        filter_args = {'next_run_before': end_time}
        self.client.list_schedules(filter_args=filter_args).AndReturn([])
        self.mox.ReplayAll()
        self.scheduler.get_schedules(end_time=end_time)
        self.mox.VerifyAll()
