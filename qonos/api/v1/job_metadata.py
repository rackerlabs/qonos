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

import qonos.api.v1.api_utils as api_utils
from qonos.common import exception
from qonos.common import wsgi
import qonos.db


class JobMetadataController(object):

    def __init__(self, db_api=None):
        self.db_api = db_api or qonos.db.get_api()

    def list(self, request, job_id):
        try:
            metadata = self.db_api.job_meta_get_all_by_job_id(job_id)
        except exception.NotFound, e:
            raise webob.exc.HTTPNotFound(explanation=e)
        return {'metadata': api_utils.serialize_metadata(metadata)}

    def update(self, request, job_id, body):
        metadata = body['metadata']
        new_meta = api_utils.deserialize_metadata(metadata)
        try:
            updated_meta = self.db_api.job_metadata_update(job_id, new_meta)
        except exception.NotFound, e:
            raise webob.exc.HTTPNotFound(explanation=e)
        return {'metadata': api_utils.serialize_metadata(updated_meta)}


def create_resource():
    """QonoS resource factory method."""
    return wsgi.Resource(JobMetadataController())
