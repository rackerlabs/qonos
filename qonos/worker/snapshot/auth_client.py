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
from qonos.common import timeutils
from qonos.openstack.common.gettextutils import _
import qonos.openstack.common.log as logging
import qonos.worker.snapshot.http_client as http_client

LOG = logging.getLogger(__name__)


class AuthClient(http_client.HttpClient):

    def __init__(self, protocol, host, port, version):
        super(AuthClient, self).__init__(protocol, host, port, version)

    def get_token(self, username, password):
        body = {
            "auth": {
                "tenantName": username,
                "passwordCredentials": {
                    "username": username,
                    "password": password
                }
            }
        }
        try:
            response = self._do_request('POST', '/tokens', body=body)
            LOG.debug('Response from auth: %s' % str(response))
        except http_client.HttpClientException as e:
            raise AuthClientException(e.message, e.response_status)

        return self._extract_token_data(response)

    @staticmethod
    def _extract_token_data(response):
        try:
            token = response['access']['token']
            token_id = token['id']
            expiration = token['expires']
            return (token_id, timeutils.normalize_time(
                    timeutils.parse_isotime(expiration)))
        except KeyError as e:
            message = ('Error retrieving token. Did not find key %s in the '
                       'response.' % str(e))
            LOG.error(message)
            raise AuthClientException(message=message)


class AuthClientException(Exception):
    message = _('Exception occurred performing authorization')

    def __init__(self, message=None, response_status=None):
        if not message:
            message = self.message
        self.response_status = response_status
        super(AuthClientException, self).__init__(message)
