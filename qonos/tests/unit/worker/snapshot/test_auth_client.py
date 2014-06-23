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
from qonos.tests import utils as test_utils
from qonos.worker.snapshot.auth_client import AuthClient
from qonos.worker.snapshot.auth_client import AuthClientException


class TestSimpleGlanceClient(test_utils.BaseTestCase):
    def setUp(self):
        super(TestSimpleGlanceClient, self).setUp()

    def tearDown(self):
        super(TestSimpleGlanceClient, self).tearDown()

    def test_extract_token_data(self):
        exp_token_id = 'my_token'
        exp_expires = timeutils.utcnow()
        response = {
            'access': {
                'token': {
                    'id': exp_token_id,
                    'expires': str(exp_expires)
                }
            }
        }

        token_id, expires = AuthClient._extract_token_data(response)
        self.assertEquals(exp_token_id, token_id)
        self.assertEquals(exp_expires, expires)

    def _get_expected_message(self, key):
        return ('Error retrieving token. Did not find key %s in the '
                'response.' % key)

    def _assert_missing_key(self, response, key):
        exp_expires = str(timeutils.utcnow())
        response = {
            'access': {
                'token': {
                    'expires': str(exp_expires)
                }
            }
        }

        exp_message = self._get_expected_message('id')

        with self.assertRaises(AuthClientException) as ace:
            AuthClient._extract_token_data(response)
            self.assertEquals(exp_message, str(ace))

    def test_extract_token_data_no_id(self):
        exp_expires = timeutils.utcnow()
        response = {
            'access': {
                'token': {
                    'expires': str(exp_expires)
                }
            }
        }

        self._assert_missing_key(response, 'id')

    def test_extract_token_data_no_expires(self):
        exp_token_id = 'my_token'
        response = {
            'access': {
                'token': {
                    'id': exp_token_id
                }
            }
        }

        self._assert_missing_key(response, 'expires')

    def test_extract_token_data_no_token(self):
        response = {
            'access': {}
        }

        self._assert_missing_key(response, 'token')

    def test_extract_token_data_no_access(self):
        response = {}

        self._assert_missing_key(response, 'access')
