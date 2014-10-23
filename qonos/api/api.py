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

from oslo.config import cfg

from qonos.common import utils
import qonos.common.wsgi as wsgi

from qonos.openstack.common.gettextutils import _
import qonos.openstack.common.log as logging

LOG = logging.getLogger(__name__)

api_opts = [
    cfg.BoolOpt('daemonized', default=False),
    cfg.IntOpt('port', default=7667),
    cfg.MultiStrOpt('action_overrides', default=[]),
    cfg.StrOpt('wsgi_log_format',
            default='%(client_ip)s "%(request_line)s" status: %(status_code)s'
                    ' len: %(body_length)s time: %(wall_seconds).7f',
            help='A python format string that is used as the template to '
                 'generate log lines. The following values can be formatted '
                 'into it: client_ip, date_time, request_line, status_code, '
                 'body_length, wall_seconds.'),
]

action_opts = [
    cfg.IntOpt('timeout_seconds', default=60),
]

CONF = cfg.CONF
CONF.register_opts(api_opts, group='api')
CONF.register_opts(action_opts, group='action_default')


class API(object):
    def __init__(self, app):
        self.app = app

    def run(self, run_once=False):
        LOG.debug(_('Starting qonos-api service'))
        # This must be done after the 'well-known' config options are loaded
        # so the list of action_overrides can be read
        self.register_action_override_cfg_opts()
        wsgi_logger = logging.getLogger('eventlet.wsgi.server')

        if CONF.api.daemonized:
            import daemon
            #NOTE(ameade): We need to preserve all open files for logging
            open_files = utils.get_qonos_open_file_log_handlers()
            with daemon.DaemonContext(files_preserve=open_files):
                wsgi.run_server(self.app, CONF.api.port,
                                log=logging.WritableLogger(wsgi_logger),
                                log_format=CONF.api.wsgi_log_format)
        else:
            wsgi.run_server(self.app, CONF.api.port,
                            log=logging.WritableLogger(wsgi_logger),
                            log_format=CONF.api.wsgi_log_format)

    def register_action_override_cfg_opts(self):
        for action in CONF.api.action_overrides:
            group = 'action_' + action
            action_opts = [
                cfg.IntOpt('timeout_seconds',
                           default=CONF.action_default.timeout_seconds),
                ]
            CONF.register_opts(action_opts, group=group)
