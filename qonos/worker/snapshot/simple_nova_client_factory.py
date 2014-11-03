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

import novaclient.extension
from novaclient.v1_1 import client
from oslo.config import cfg
import rax_scheduled_images_python_novaclient_ext

import qonos.openstack.common.log as logging


LOG = logging.getLogger(__name__)

nova_client_factory_opts = [
    cfg.StrOpt('auth_protocol', default="http"),
    cfg.StrOpt('auth_host',
               default="127.0.0.1"),
    cfg.IntOpt('auth_port', default=5000),
    cfg.StrOpt('auth_version', default='v2.0'),
    cfg.StrOpt('nova_admin_user', default='admin_user'),
    cfg.StrOpt('nova_admin_password', default='admin_pass'),
    cfg.BoolOpt('http_log_debug', default=False),
    cfg.BoolOpt('nova_auth_insecure', default=False),
]

CONF = cfg.CONF
CONF.register_opts(nova_client_factory_opts,
                   group='nova_client_factory')


class NovaClientFactory(object):

    def __init__(self):
        self.nova_client = None
        self.current_job_id = None

    def get_nova_client(self, job):
        if(self.nova_client is not None and
           self.current_job_id == job['id']):
            return self.nova_client

        self.current_job_id = None
        self.nova_client = None

        auth_protocol = CONF.nova_client_factory.auth_protocol
        auth_host = CONF.nova_client_factory.auth_host
        auth_port = CONF.nova_client_factory.auth_port
        auth_version = CONF.nova_client_factory.auth_version

        auth_url = "%s://%s:%d/%s" % (auth_protocol, auth_host, auth_port,
                                      auth_version)

        user = CONF.nova_client_factory.nova_admin_user
        password = CONF.nova_client_factory.nova_admin_password
        debug = CONF.nova_client_factory.http_log_debug
        insecure = CONF.nova_client_factory.nova_auth_insecure
        tenant = job['tenant']

        sched_image_ext = novaclient.extension.Extension(
            'rax_scheduled_images_python_novaclient_ext',
            rax_scheduled_images_python_novaclient_ext)

        self.nova_client = client.Client(user,
                                         password,
                                         project_id=tenant,
                                         auth_url=auth_url,
                                         insecure=insecure,
                                         extensions=[sched_image_ext],
                                         http_log_debug=debug)
        self.current_job_id = job['id']

        return self.nova_client
