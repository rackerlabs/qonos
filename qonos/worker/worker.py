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

import errno
import os
import signal
import socket
import time

from oslo.config import cfg

from qonos.common import importutils
from qonos.common import utils
from qonos.openstack.common.gettextutils import _
import qonos.openstack.common.log as logging


LOG = logging.getLogger(__name__)

# TODO(WORKER) action_type should be queried from the job processor
worker_opts = [
    cfg.IntOpt('job_poll_interval', default=5,
               help=_('Interval to poll api for ready jobs in seconds')),
    cfg.StrOpt('api_endpoint', default='localhost',
               help=_('Address of the QonoS API server')),
    cfg.IntOpt('api_port', default=7667,
               help=_('Port on which to contact QonoS API server')),
    cfg.BoolOpt('daemonized', default=False,
                help=_('True to run the worker as a daemon')),
    cfg.StrOpt('action_type', default='None',
               help=_('A string identifying the type of action this '
                      'worker handles')),
    cfg.StrOpt('processor_class', default=None,
               help=_('The fully qualified class name of the processor '
                      'to use in this worker')),
    cfg.BoolOpt('fork_job_process', default=False,
                help=_('True to fork a child process for job processing')),
]

CONF = cfg.CONF
CONF.register_opts(worker_opts, group='worker')


class Worker(object):
    def __init__(self, client_factory, processor=None):
        self.client = client_factory(CONF.worker.api_endpoint,
                                     CONF.worker.api_port)
        if not processor:
            processor = importutils.import_object(CONF.worker.processor_class)

        self.processor = processor
        self.worker_id = None
        self.host = socket.gethostname()
        self.running = False
        self.pid = None
        self._child_pid = None

    def run(self, run_once=False, poll_once=False):
        LOG.info(_('Starting qonos worker service'))

        if CONF.worker.daemonized:
            LOG.debug(_('Entering daemon mode'))
            import daemon
            #NOTE(ameade): We need to preserve all open files for logging
            open_files = utils.get_qonos_open_file_log_handlers()
            signal_map = self._signal_map()
            with daemon.DaemonContext(files_preserve=open_files,
                                      signal_map=signal_map):
                self._run_loop(run_once, poll_once)
        else:
            for sig, action in self._signal_map().iteritems():
                signal.signal(sig, action)
            self._run_loop(run_once, poll_once)

    def _signal_map(self):
        return {
            signal.SIGTERM: self._terminate,
            signal.SIGHUP: self._terminate,
        }

    def init_worker(self):
        self.running = True
        self.pid = os.getpid()
        self.processor.init_processor(self)
        self.worker_id = self._register_worker()

    def _process_job(self, job):
        """Method that invokes the JobProcessor.process_job with the given job.

        This method is common for both inline and forked job processing.
        Invoked by process_job() and child_process_main() methods
        """
        try:
            self.processor.process_job(job)
        except Exception as e:
            msg = _("Worker %(worker_id)s Error processing job:"
                    " %(job)s")
            LOG.exception(msg % {'worker_id': self.worker_id,
                                 'job': job['id']})
            self.update_job(job['id'], 'ERROR', error_message=unicode(e))

    def process_job(self, job):
        LOG.debug(_('Processing job: %s') % job)

        if CONF.worker.fork_job_process:
            self._fork_process_job(job)
        else:
            self._process_job(job)

    def _fork_process_job(self, job):
        """This method forks a child process and waits for it to complete."""

        child_pid = os.fork()
        if child_pid == 0:
            self.child_process_main(job)
        else:
            self._child_pid = child_pid

            LOG.debug(_("Worker %(worker_id)s forked %(child_pid)s "
                        "for processing job %(job_id)s") %
                      {'worker_id': self.worker_id,
                       'child_pid': self._child_pid,
                       'job_id': job['id']})

            while True:
                try:
                    os.waitpid(child_pid, 0)
                    break
                except OSError as e:
                    if e.errno != errno.EINTR:
                        raise

            LOG.debug(_("End of processing of job %(job_id)s "
                        "by forked %(child_pid)s from "
                        "worker %(worker_id)s") %
                      {'worker_id': self.worker_id,
                       'child_pid': self._child_pid,
                       'job_id': job['id']})

    def child_process_main(self, job):
        """This is the entry point of the newly spawned child process."""

        self._process_job(job)

        # os._exit() is the way to exit from childs after a fork(), in
        # constrast to the regular sys.exit()
        os._exit(0)

    def _run_loop(self, run_once=False, poll_once=False):
        self.init_worker()

        while self.running:
            time_before = time.time()

            job = self._poll_for_next_job(poll_once)
            if job:
                try:
                    self.process_job(job)
                except Exception as e:
                    LOG.exception(e)
                finally:
                    self._child_pid = None

            time_after = time.time()

            # Ensure that we wait at least job_poll_interval between jobs
            time_delta = time_after - time_before
            if time_delta < CONF.worker.job_poll_interval:
                time.sleep(CONF.worker.job_poll_interval - time_delta)

            if run_once:
                self.running = False

        LOG.info(_('Worker is shutting down'))
        self._unregister_worker()
        self.processor.cleanup_processor()

    def _register_worker(self):
        LOG.info(_('Registering worker with pid %s') % str(self.pid))
        while self.running:
            worker = None
            with utils.log_warning_and_dismiss_exception(LOG):
                worker = self.client.create_worker(self.host, self.pid)

            if worker:
                msg = _('Worker has been registered with ID: %s')
                LOG.info(msg % worker['id'])
                return worker['id']

            time.sleep(CONF.worker.job_poll_interval)

    def _unregister_worker(self):
        LOG.info(_('Unregistering worker. ID: %s') % self.worker_id)
        with utils.log_warning_and_dismiss_exception(LOG):
            self.client.delete_worker(self.worker_id)

    def _terminate(self, signum, frame):
        LOG.debug(_('Received signal %s - will exit') % str(signum))
        self.running = False

        if CONF.worker.fork_job_process and self._child_pid:
            os.kill(self._child_pid, signal.SIGTERM)
        else:
            self.processor.stop_processor()

    def _poll_for_next_job(self, poll_once=False):
        job = None

        while job is None and self.running:
            time.sleep(CONF.worker.job_poll_interval)
            LOG.debug(_("Attempting to get next job from API"))
            job = None
            with utils.log_warning_and_dismiss_exception(LOG):
                job = self.client.get_next_job(self.worker_id,
                                               CONF.worker.action_type)['job']

            if poll_once:
                break

        return job

    def get_qonos_client(self):
        return self.client

    def update_job(self, job_id, status, timeout=None, error_message=None):
        msg = (_("Worker: [%(worker_id)s] updating "
               "job [%(job_id)s] Status: %(status)s") %
               {'worker_id': self.worker_id,
                'job_id': job_id,
                'status': status})

        if timeout:
            msg += _(" Timeout: %s") % str(timeout)

        if error_message:
            msg += _(" Error message: %s") % error_message

        LOG.debug(msg)
        try:
            return self.client.update_job_status(job_id, status, timeout,
                                                 error_message)
        except Exception:
            LOG.exception(_("Failed to update job status."))

    def update_job_metadata(self, job_id, metadata):
        return self.client.update_job_metadata(job_id, metadata)


class JobProcessor(object):
    def __init__(self):
        self.worker = None
        self._stopping = False

    def get_qonos_client(self):
        return self.worker.get_qonos_client()

    def send_notification(self, event_type, payload, level='INFO'):
        utils.generate_notification(None, event_type, payload, level)

    def send_notification_job_update(self, payload, level='INFO'):
        self.send_notification('qonos.job.update', payload, level)

    def send_notification_start(self, payload, level='INFO'):
        self.send_notification('qonos.job.run.start', payload, level)

    def send_notification_end(self, payload, level='INFO'):
        self.send_notification('qonos.job.run.end', payload, level)

    def send_notification_retry(self, payload, level='INFO'):
        self.send_notification('qonos.job.retry', payload, level)

    def send_notification_job_failed(self, payload, level='ERROR'):
        self.send_notification('qonos.job.failed', payload, level)

    def update_job(self, job_id, status, timeout=None, error_message=None):
        return self.worker.update_job(job_id, status, timeout=timeout,
                                      error_message=error_message)

    def update_job_metadata(self, job_id, metadata):
        return self.worker.update_job_metadata(job_id, metadata)

    def init_processor(self, worker):
        """
        Override to perform processor-specific setup.
        Implementations should call the superclass implementation
        to insure the worker attribute is initialized.

        Called BEFORE the worker is registered with QonoS.
        """
        self.worker = worker

    def process_job(self, job):
        """
        Override to perform actual job processing.

        Called each time a new job is fetched.
        """
        pass

    def cleanup_processor(self):
        """
        Override to perform processor-specific setup.

        Called AFTER the worker is unregistered from QonoS.
        """
        pass

    def stop_processor(self):
        self._stopping = True

    @property
    def stopping(self):
        return self._stopping
