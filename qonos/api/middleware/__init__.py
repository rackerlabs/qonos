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
from qonos.common import wsgi as wsgi

import webob
import webob.exc

from qonos.openstack.common import log as logging

LOG = logging.getLogger(__name__)


class RequestLogger(wsgi.Middleware):
    """Logs qonos request id, if present, before and after processing a request

    The request id is determined by looking for the header
    'x-qonos-request-id'. """

    @webob.dec.wsgify(RequestClass=wsgi.Request)
    def __call__(self, req):
        req_id = req.headers.get('x-qonos-request-id')

        if req_id is not None:
            LOG.info('Processing Qonos request: %s' % req_id)

        resp = req.get_response(self.application)

        if req_id is not None:
            LOG.info('Returning Qonos request: %s' % req_id)

        return resp

    @classmethod
    def factory(cls, global_conf, **local_conf):
        def filter(app):
            return cls(app)
        return filter
