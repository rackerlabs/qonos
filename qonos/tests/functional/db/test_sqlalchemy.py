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
import logging
import mock
import StringIO
import sys


from qonos.common import timeutils
import qonos.db.sqlalchemy.api
from qonos.openstack.common.gettextutils import _
from qonos.tests.functional.db import base
from qonos.tests import utils


def setUpModule():
    """Stub in get_db and reset_db for testing the simple db api."""
    base.db_api = qonos.db.sqlalchemy.api
    base.db_api.configure_db()


def tearDownModule():
    """Reset get_db and reset_db for cleanliness."""
    base.db_api = None


#NOTE(ameade): Pull in cross driver db tests
thismodule = sys.modules[__name__]
utils.import_test_cases(thismodule, base, suffix="_Sqlalchemy_DB")


class TestSQLAlchemyOptimisticLocking(base.TestJobsDBGetNextJobApi):

    def _setup_db_api_log_fixture(self, stream):
        db_api_log = logging.getLogger('qonos.db.sqlalchemy.api')
        db_api_log.setLevel(logging.WARN)
        handler = logging.StreamHandler(stream)
        handler.setFormatter(logging.Formatter('%(message)s'))
        db_api_log.addHandler(handler)

        self.addCleanup(db_api_log.removeHandler, handler)

    def _prepare_same_job_for_workers(self, job_id):
        same_job_ref_1 = base.db_api._job_get_by_id(job_id)
        same_job_ref_2 = base.db_api._job_get_by_id(job_id)

        self.assertNotEqual(same_job_ref_1, same_job_ref_2)
        self.assertEqual(same_job_ref_1['id'], same_job_ref_2['id'])
        self.assertIsNone(same_job_ref_1['worker_id'])
        self.assertIsNone(same_job_ref_2['worker_id'])

        return same_job_ref_1, same_job_ref_2

    def _assign_jobs_for_concurrent_workers(self, workers):
        new_timeout = timeutils.utcnow() + datetime.timedelta(hours=3)

        worker1_job = base.db_api.job_get_and_assign_next_by_action(
            'snapshot', workers[0], 2, new_timeout)
        worker2_job = base.db_api.job_get_and_assign_next_by_action(
            'snapshot', workers[1], 2, new_timeout)

        return worker1_job, worker2_job

    def test_get_and_assign_next_job_fails_on_job_update_with_stale_data(self):
        stream = StringIO.StringIO()
        self._setup_db_api_log_fixture(stream)
        self._create_jobs(10, self.job_fixture_1)

        with mock.patch.object(base.db_api,
                               '_job_get_next_by_action') as mocked_next_job:
            same_job_ref_1, same_job_ref_2 = \
                self._prepare_same_job_for_workers(self.jobs[0]['id'])
            mocked_next_job.side_effect = [same_job_ref_1, same_job_ref_2]

            workers = ['CONCURRENT_WORKER-1', 'CONCURRENT_WORKER-2']

            worker1_job, worker2_job = \
                self._assign_jobs_for_concurrent_workers(workers)

            # assertion for successful assigned job
            self.assertIsNotNone(worker1_job)
            self.assertEqual(worker1_job['id'], same_job_ref_1['id'])
            self.assertEqual(workers[0], worker1_job['worker_id'])

            # assertion for failed job assignment due to StaleDataError
            self.assertIsNone(worker2_job)
            stale_data_err_msg = _(
                '[JOB2WORKER] StaleDataError:'
                ' Could not assign the job to worker_id: %(worker_id)s'
                ' Job already assigned to another worker,'
                ' job_id: %(job_id)s.') % {'worker_id': workers[1],
                                           'job_id': same_job_ref_2['id']}
            self.assertEqual(stale_data_err_msg,
                             stream.getvalue().rstrip('\n'))
