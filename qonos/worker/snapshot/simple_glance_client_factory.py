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

from oslo.config import cfg
from qonos.common import timeutils
import qonos.openstack.common.log as logging
import qonos.worker.snapshot.auth_client as auth_client
import qonos.worker.snapshot.simple_glance_client as glance_client


LOG = logging.getLogger(__name__)


glance_client_factory_opts = [
    cfg.StrOpt('auth_host', default="http://127.0.0.1"),
    cfg.IntOpt('auth_port', default=5000),
    cfg.StrOpt('auth_version', default='v2.0'),
    cfg.StrOpt('glance_admin_user', default='admin_user'),
    cfg.StrOpt('glance_admin_password', default='admin_pass'),
    cfg.IntOpt('glance_api_version', default=1),
    cfg.StrOpt('glance_host',
               default='$my_ip',
               help='Default glance hostname or IP address'),
    cfg.IntOpt('glance_port',
               default=9292,
               help='Default glance port'),
    cfg.StrOpt('glance_protocol',
                default='http',
                help='Default protocol to use when connecting to glance. '
                     'Set to https for SSL.'),
    cfg.BoolOpt('glance_api_insecure',
                default=False,
                help='Allow to perform insecure SSL (https) requests to '
                     'glance'),
]

CONF = cfg.CONF
CONF.register_opts(glance_client_factory_opts,
                   group='glance_client_factory')


class GlanceClientFactory(object):

    def __init__(self):
        self.glance_client = None
        self.current_job_id = None
        self.auth_client = self._get_auth_client()
        self.token = None
        self.expiration = timeutils.utcnow()

    def get_glance_client(self):
        if (self.glance_client is not None and
            self.token is not None and
            self.expiration > timeutils.utcnow()):
            return self.glance_client

        # Clear these variables in case the auth / client creation fail
        self.glance_client = None
        self.token = None
        self.expiration = timeutils.utcnow()

        user = CONF.glance_client_factory.glance_admin_user
        password = CONF.glance_client_factory.glance_admin_password
        token, expiration = self.auth_client.get_token(user, password)

        glance_version = CONF.glance_client_factory.glance_api_version
        glance_host = CONF.glance_client_factory.glance_host
        glance_port = CONF.glance_client_factory.glance_port
        glance_protocol = CONF.glance_client_factory.glance_protocol
        glance_api_insecure = CONF.glance_client_factory.glance_api_insecure

        glance_endpoint = "%s://%s:%s" % (glance_protocol, glance_host,
                                          glance_port)

        self.glance_client = glance_client.GlanceClient(
            version=glance_version, endpoint=glance_endpoint, token=token,
            insecure=glance_api_insecure)

        self.token = token
        self.expiration = expiration

        return self.glance_client

    def _get_auth_client(self):
        auth_host = CONF.glance_client_factory.auth_host
        auth_port = CONF.glance_client_factory.auth_port
        auth_version = CONF.glance_client_factory.auth_version
        return auth_client.AuthClient(auth_host, auth_port, auth_version)
