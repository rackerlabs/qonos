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
import copy
import webob.exc

from qonos.api import api
from qonos.api.v1 import api_utils
from qonos.common import exception
from qonos.common import timeutils
from qonos.common import utils
import qonos.db
from qonos.openstack.common._i18n import _
from qonos.openstack.common import wsgi


CONF = api.CONF


class WorkersController(object):

    def __init__(self, db_api=None):
        self.db_api = db_api or qonos.db.get_api()

    def _get_request_params(self, request):
        params = {}
        params['limit'] = request.params.get('limit')
        params['marker'] = request.params.get('marker')
        return params

    def list(self, request):
        params = self._get_request_params(request)
        try:
            params = utils.get_pagination_limit(params)
        except exception.Invalid as e:
            raise webob.exc.HTTPBadRequest(explanation=str(e))
        try:
            workers = self.db_api.worker_get_all(params=params)
        except exception.NotFound:
            raise webob.exc.HTTPNotFound()
        [utils.serialize_datetimes(worker) for worker in workers]
        return {'workers': workers}

    def create(self, request, body):
        worker = self.db_api.worker_create(body.get('worker'))
        utils.serialize_datetimes(worker)
        return {'worker': worker}

    def get(self, request, worker_id):
        try:
            worker = self.db_api.worker_get_by_id(worker_id)
        except exception.NotFound:
            msg = _('Worker %s could not be found.') % worker_id
            raise webob.exc.HTTPNotFound(explanation=msg)
        utils.serialize_datetimes(worker)
        return {'worker': worker}

    def delete(self, request, worker_id):
        try:
            self.db_api.worker_delete(worker_id)
        except exception.NotFound:
            msg = _('Worker %s could not be found.') % worker_id
            raise webob.exc.HTTPNotFound(explanation=msg)

    def get_next_job(self, request, worker_id, body):
        action = body.get('action')
        try:
            # Check that worker exists
            self.db_api.worker_get_by_id(worker_id)
        except exception.NotFound:
            msg = _('Worker %s could not be found.') % worker_id
            raise webob.exc.HTTPNotFound(explanation=msg)

        new_timeout = api_utils.get_new_timeout_by_action(action)

        while True:
            job = self.db_api.job_get_and_assign_next_by_action(
                action, worker_id, new_timeout)
            if job is None:
                break

            utils.serialize_datetimes(job)
            api_utils.serialize_job_metadata(job)

            if self.validate_job(job):
                break

        return {'job': job}

    def validate_job(self, job_payload):
        job = copy.deepcopy(job_payload)
        max_retry = api_utils.job_get_max_retry(job['action'])
        if job['retry_count'] >= max_retry:
            self._notify_job_failed_status(job, 'MAX_RETRIED')
            return False

        now = timeutils.utcnow()
        hard_timeout = timeutils.normalize_time(
            timeutils.parse_isotime(job['hard_timeout']))
        if hard_timeout <= now:
            self._notify_job_failed_status(job, 'HARD_TIMED_OUT')
            return False

        return True

    def _update_job_status(self, job_id, status):
        values = {'status': status.upper()}

        try:
            return self.db_api.job_update(job_id, values)
        except exception.NotFound:
            msg = (_('Job %s could not be found while updating status to %s.')
                   % (job_id, status))
            raise webob.exc.HTTPNotFound(explanation=msg)

    def _notify_job_failed_status(self, job, status):
        job = self._update_job_status(job['id'], status)
        job['error_message'] = ''
        job = {'job': job}
        utils.generate_notification(None,
                                    'qonos.job.failed',
                                    job,
                                    'ERROR')


def create_resource():
    """QonoS resource factory method."""
    return wsgi.Resource(WorkersController())
