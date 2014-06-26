#    Copyright 2014 Rackspace
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
import httplib
try:
    import json
except ImportError:
    import simplejson as json


from qonos.openstack.common.gettextutils import _
import qonos.openstack.common.log as logging


LOG = logging.getLogger(__name__)


class HttpClient(object):

    def __init__(self, protocol, host, port, version):
        if protocol is None or (protocol.lower() not in ['http', 'https']):
            raise HttpClientException(message='Invalid protocol: %s' %
                                              str(protocol))
        self.protocol = protocol
        self.host = host
        self.port = port
        self.version = version

    def _get_connection(self):
        if self.protocol.lower() == 'https':
            return httplib.HTTPSConnection(self.host, self.port)
        elif self.protocol.lower() == 'http':
            return httplib.HTTPConnection(self.host, self.port)

    def _do_request(self, method, url, auth_token=None, body=None):
        conn = self._get_connection()
        url = "/%s%s" % (self.version, url)
        headers = {
                   'Content-Type': 'application/json',
                   'Accept': 'application/json'
                  }

        if auth_token:
            #NOTE: ensure auth_token is not unicode
            headers['X-Auth-Token'] = str(auth_token)

        if body and isinstance(body, dict):
            body = json.dumps(body)

        try:
            conn.request(method, url, body=body, headers=headers)
        except Exception, e:
            LOG.debug("Exception %s" % str(e))
            msg = 'Could not contact Authentication API'
            raise HttpClientException(msg)

        response = conn.getresponse()

        if response.status not in (200, 203):
            msg = ("Response status: %(status)s, Response reason: %(reason)s"
                    % {"status": response.status, "reason": response.reason})
            LOG.error(msg)
            raise HttpClientException(msg, response_status=response.status)

        if method != 'DELETE':
            body = response.read()
            if body != '':
                return json.loads(body)


class HttpClientException(Exception):
    message = _('Exception occurred performing HTTP request')

    def __init__(self, message=None, response_status=None):
        if not message:
            message = self.message
        self.response_status = response_status
        super(HttpClientException, self).__init__(message)
