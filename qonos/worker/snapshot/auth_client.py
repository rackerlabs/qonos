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

    def __init__(self, host, port, version):
        super(AuthClient, self).__init__(host, port, version)

    def get_token(self, username, password):
        body = {"auth": {
                         "passwordCredentials": {"username": username,
                                                 "password": password
                                                }
                        }
               }
        try:
            response = self._do_request('POST', '/tokens', body=body)
        except http_client.HttpClientException as e:
            raise AuthClientException(e.message, e.response_status)

        token = response['access']['token']['id']
        expiration = response['access']['token']['expires']
        return (token, timeutils.normalize_time(
                timeutils.parse_isotime(expiration)))


class AuthClientException(Exception):
    message = _('Exception occurred performing authorization')

    def __init__(self, message=None, response_status=None):
        if not message:
            message = self.message
        self.response_status = response_status
        super(AuthClientException, self).__init__(message)
