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

import webob.exc

from qonos.api import api
from qonos.api.v1 import api_utils
from qonos.common import exception
from qonos.common import timeutils
from qonos.common import utils
import qonos.db
from qonos.openstack.common.gettextutils import _
from qonos.openstack.common import wsgi


CONF = api.CONF


class JobsController(object):

    def __init__(self, db_api=None):
        self.db_api = db_api or qonos.db.get_api()

    def list(self, request):
        params = request.params.copy()

        try:
            params = utils.get_pagination_limit(params)
        except exception.Invalid as e:
            raise webob.exc.HTTPBadRequest(explanation=str(e))

        if 'status' in params:
            params['status'] = str(params['status']).upper()

        if 'timeout' in params:
            timeout = timeutils.parse_isotime(params['timeout'])
            params['timeout'] = timeutils.normalize_time(timeout)

        if 'hard_timeout' in params:
            hard_timeout = timeutils.parse_isotime(params['hard_timeout'])
            params['hard_timeout'] = timeutils.normalize_time(hard_timeout)

        try:
            jobs = self.db_api.job_get_all(params)
        except exception.NotFound:
            raise webob.exc.HTTPNotFound()

        limit = params.get('limit')
        if len(jobs) != 0 and len(jobs) == limit:
            next_page = '/v1/jobs?marker=%s' % jobs[-1].get('id')
        else:
            next_page = None

        for job in jobs:
            utils.serialize_datetimes(job)
            api_utils.serialize_job_metadata(job)

        links = [{'rel': 'next', 'href': next_page}]
        return {'jobs': jobs, 'jobs_links': links}

    def create(self, request, body):
        if (body is None or body.get('job') is None or
                body['job'].get('schedule_id') is None):
            raise webob.exc.HTTPBadRequest()
        job = body['job']

        try:
            schedule = self.db_api.schedule_get_by_id(job['schedule_id'])
        except exception.NotFound:
            raise webob.exc.HTTPNotFound()

        # Check integrity of schedule and update next run
        expected_next_run = job.get('next_run')
        if expected_next_run:
            try:
                expected_next_run = timeutils.parse_isotime(expected_next_run)
                expected_next_run = expected_next_run.replace(tzinfo=None)
            except ValueError as e:
                msg = _('Invalid "next_run" value. Must be ISO 8601 format')
                raise webob.exc.HTTPBadRequest(explanation=msg)

        next_run = api_utils.schedule_to_next_run(schedule, timeutils.utcnow())
        next_run = next_run.replace(tzinfo=None)
        try:
            self.db_api.schedule_test_and_set_next_run(schedule['id'],
                        expected_next_run, next_run)

        except exception.NotFound:
            msg = _("Specified next run does not match the current next run"
                    " value. This could mean schedule has either changed"
                    "or has already been scheduled since you last expected.")
            raise webob.exc.HTTPConflict(explanation=msg)

        # Update schedule last_scheduled
        values = {}
        values['last_scheduled'] = timeutils.utcnow()
        self.db_api.schedule_update(schedule['id'], values)

        # Create job
        values = {}
        values.update(job)
        values['tenant'] = schedule['tenant']
        values['action'] = schedule['action']
        values['status'] = 'QUEUED'

        job_metadata = []
        for metadata in schedule['schedule_metadata']:
            job_metadata.append({
                    'key': metadata['key'],
                    'value': metadata['value']
                    })

        values['job_metadata'] = job_metadata

        job_action = values['action']
        if not 'timeout' in values:
            values['timeout'] = api_utils.get_new_timeout_by_action(job_action)
            values['hard_timeout'] = \
                api_utils.get_new_timeout_by_action(job_action)

        job = self.db_api.job_create(values)
        utils.serialize_datetimes(job)
        api_utils.serialize_job_metadata(job)
        job = {'job': job}
        utils.generate_notification(None, 'qonos.job.create', job, 'INFO')
        return job

    def get(self, request, job_id):
        try:
            job = self.db_api.job_get_by_id(job_id)
        except exception.NotFound:
            raise webob.exc.HTTPNotFound
        utils.serialize_datetimes(job)
        api_utils.serialize_job_metadata(job)
        return {'job': job}

    def delete(self, request, job_id):
        try:
            self.db_api.job_delete(job_id)
        except exception.NotFound:
            msg = _('Job %s could not be found.') % job_id
            raise webob.exc.HTTPNotFound(explanation=msg)

    def update_status(self, request, job_id, body):
        status = body.get('status')
        if not status:
            raise webob.exc.HTTPBadRequest()

        values = {'status': status['status'].upper()}
        if 'timeout' in status:
            timeout = timeutils.parse_isotime(status['timeout'])
            values['timeout'] = timeutils.normalize_time(timeout)

        job = None
        try:
            job = self.db_api.job_update(job_id, values)
        except exception.NotFound:
            msg = _('Job %s could not be found.') % job_id
            raise webob.exc.HTTPNotFound(explanation=msg)

        err_statuses = ['ERROR', 'CANCELLED', 'HARD_TIMED_OUT', 'MAX_RETRIED']
        if status['status'].upper() in err_statuses:
            values = self._get_error_values(status, job)
            self.db_api.job_fault_create(values)

        return {'status': {'status': job['status'],
                           'timeout': job['timeout']}}

    def _get_error_values(self, status, job):
        api_utils.serialize_job_metadata(job)
        job_metadata = job['metadata']
        values = {
            'job_id': job['id'],
            'action': job['action'],
            'schedule_id': job['schedule_id'],
            'tenant': job['tenant'],
            'worker_id': job['worker_id'] or 'UNASSIGNED',
            'job_metadata': str(job_metadata),
            }
        if 'error_message' in status:
            values['message'] = status['error_message']
        else:
            values['message'] = None

        return values

    def _job_get_timeout(self, action):
        group = 'action_' + action
        if group not in CONF:
            group = 'action_default'
        return CONF.get(group).timeout_seconds


def create_resource():
    """QonoS resource factory method."""
    return wsgi.Resource(JobsController())
