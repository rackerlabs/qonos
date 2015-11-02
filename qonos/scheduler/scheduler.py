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

import signal
import time

from oslo_config import cfg

from qonos.common import timeutils
from qonos.common import utils
from qonos.openstack.common._i18n import _
import qonos.openstack.common.log as logging
from qonos.qonosclient import exception as client_exc

LOG = logging.getLogger(__name__)

scheduler_opts = [
    cfg.IntOpt('job_schedule_interval', default=5,
               help=_('Interval to poll api for ready jobs in seconds')),
    cfg.StrOpt('api_endpoint', default='localhost'),
    cfg.IntOpt('api_port', default=7667),
]

CONF = cfg.CONF
CONF.register_opts(scheduler_opts, group='scheduler')


class Scheduler(object):
    def __init__(self, client_factory):
        self.client = client_factory(CONF.scheduler.api_endpoint,
                                     CONF.scheduler.api_port)

    def run(self, run_once=False):
        LOG.debug(_('Starting qonos scheduler service'))
        self.running = True

        self._run_loop(run_once)

    def _signal_map(self):
        return {
            signal.SIGTERM: self._terminate,
            signal.SIGHUP: self._terminate,
        }

    def _run_loop(self, run_once=False):
        next_run = None
        current_run = None

        while self.running:
            current_run = timeutils.isotime()
            next_run = time.time() + CONF.scheduler.job_schedule_interval

            # do work
            with utils.log_warning_and_dismiss_exception(LOG):
                self.enqueue_jobs(end_time=current_run)

            # if shutdown hasn't been requested, do nothing until next run
            if self.running:
                seconds = next_run - time.time()
                if seconds > 0:
                    time.sleep(seconds)
                else:
                    msg = _('Scheduling of jobs took longer than expected.')
                    LOG.warn(msg)

            if run_once:
                break

        LOG.info(_('Scheduler is shutting down'))

    def _terminate(self, signum, frame):
        LOG.debug(_('Received signal %s - will exit') % str(signum))
        self.running = False

    def enqueue_jobs(self, start_time=None, end_time=None):
        LOG.debug(_('Fetching schedules to process'))
        schedules = self.get_schedules(start_time, end_time)
        if schedules:
            LOG.info(_('Creating %d jobs') % len(schedules))
            for schedule in schedules:
                try:
                    self.client.create_job(schedule['id'],
                                           schedule.get('next_run'))
                except client_exc.Duplicate:
                    msg = _("Job for schedule %s has already been created")
                    LOG.info(msg % schedule['id'])

    def get_schedules(self, start_time=None, end_time=None):
        filter_args = {'next_run_before': end_time}

        if start_time:
            filter_args['next_run_after'] = start_time

        return self.client.list_schedules(filter_args=filter_args)
