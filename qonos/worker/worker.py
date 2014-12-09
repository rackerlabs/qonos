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

import os
import signal
import socket
import time
import thread

from oslo.config import cfg

from qonos.common import utils
from qonos.openstack.common.gettextutils import _
from qonos.openstack.common import importutils
import qonos.openstack.common.log as logging

LOG = logging.getLogger(__name__)

# TODO(WORKER) action_type should be queried from the job processor
worker_opts = [
    cfg.IntOpt('job_poll_interval', default=5,
               help=_('Interval to poll api for ready jobs in seconds. May be'
                      'updated via SIGHUP.')),
    cfg.StrOpt('api_endpoint', default='localhost',
               help=_('Address of the QonoS API server')),
    cfg.IntOpt('api_port', default=7667,
               help=_('Port on which to contact QonoS API server')),
    cfg.StrOpt('action_type', default='None',
               help=_('A string identifying the type of action this '
                      'worker handles')),
    cfg.StrOpt('processor_class', default=None,
               help=_('The fully qualified class name of the processor '
                      'to use in this worker')),
    cfg.IntOpt('max_child_processes', default=0,
               help=_('The maximum number of child processes to fork. Set to'
                      '0 to disable forking. May be updated via SIGHUP, but'
                      'enabling / disabling forking requires restart.')),
]

CONF = cfg.CONF
CONF.register_opts(worker_opts, group='worker')
LOCK = thread.allocate_lock()


def get_config_value(conf_key):
    LOCK.acquire()
    value = getattr(CONF.worker, conf_key)
    LOCK.release()
    return value


def Worker(client_factory, processor_class=None):
    max_child_processes = get_config_value("max_child_processes")

    if max_child_processes > 0:
        return MultiChildWorker(client_factory, processor_class)
    else:
        return SingleProcessWorker(client_factory, processor_class)


class WorkerBase(object):
    def __init__(self, client_factory, processor_class=None):
        self.client = client_factory(get_config_value("api_endpoint"),
                                     get_config_value("api_port"))
        if not processor_class:
            processor_class = importutils.import_class(
                get_config_value("processor_class"))

        self.processor_class = processor_class
        self.processor = None
        self.worker_id = None
        self.host = socket.gethostname()
        self.running = False
        self.parent_pid = os.getpid()

    def run(self, run_once=False, poll_once=False):
        LOG.info(_('[%s] Starting qonos worker service')
                 % self.get_worker_tag())

        for sig, action in self._signal_map().iteritems():
            signal.signal(sig, action)
        self._run_loop(run_once, poll_once)

    def _signal_map(self):
        return {
            signal.SIGTERM: self._terminate,
            signal.SIGHUP: self._update,
            signal.SIGUSR1: self._dump_config,
        }

    def _terminate(self, signum, frame):
        LOG.debug(_('[%(worker_tag)s] Received signal %(signum)s - will exit')
                  % {'worker_tag': self.get_worker_tag(),
                     'signum': str(signum)})
        self.running = False

        self._on_terminate(signum)

    def _update(self, signum, frame):
        LOG.warn(_('[%(worker_tag)s] Received signal %(signum)s - updating') %
                 {'worker_tag': self.get_worker_tag(),
                  'signum': str(signum)})
        if self._can_reload_configuration():
            self._reload_configuration()
        else:
            LOG.warn(_('[%(worker_tag)s] This worker process does not support '
                       'reloading of configuration values.') %
                    {'worker_tag': self.get_worker_tag()})

    def _reload_configuration(self):
        LOG.warn(_('[%(worker_tag)s] Reloading configuration values') %
                 {'worker_tag': self.get_worker_tag()})
        LOCK.acquire()
        CONF.reload_config_files()
        LOCK.release()

    def _dump_config(self, signum, frame):
        LOG.warn(_('[%(worker_tag)s] Received signal %(signum)s - '
                   'reloading configs') %
                 {'worker_tag': self.get_worker_tag(),
                  'signum': str(signum)})
        LOG.warn("Configured max_child_processes: %d" % get_config_value("max_child_processes"))

    def _on_terminate(self, signum):
        """
        Override in subclasses to perform any worker-specific shutdown tasks.
        Note that the run_loop is still going at this point and this is
        primarily intended as an opportunity to flag the processor to stop.
        Any worker-level cleanup that needs to happen after the run_loop has
        quit should happen in the _on_shutdown method.
        """
        pass

    def _on_shutdown(self):
        """
        Called after the run_loop has quit and before the worker has
        unregistered from the API.
        """
        pass

    def _can_reload_configuration(self):
        """
        Override in subclasses to indicate if the worker (or subprocess)
        does not support reloading of the configuration.

        Most likely this would be used in child processes since once started
        the child should probably run to completion using the initial config
        values when it was started.
        """
        return True

    def _can_accept_job(self):
        """
        Override in subclasses to indicate if the worker is ready to accept
        another job or if polling should be skipped for now.
        """
        pass

    def process_job(self, job):
        """
        Override in subclasses to do any special tasks (e.g. forking a
        subprocess) to perform actual job processing.

        To actually invoke the processing of the job in the configured
        subprocessor, subclasses should call self._process_job(job)
        when ready.
        """
        pass

    def get_worker_tag(self):
        """
        Return a string uniquely identifying this worker for logging.
        """
        tag = 'W: '
        if self.worker_id is None:
            tag += 'Unregistered'
        else:
            tag += self.worker_id

        tag += ' P:%s' % self.parent_pid

        return tag

    def init_worker(self):
        self.running = True
        self.worker_id = self._register_worker()

    def _process_job(self, job):
        """Method that invokes the JobProcessor.process_job with the given job.

        This method is common for both inline and forked job processing.
        Invoked by process_job() and child_process_main() methods
        """
        try:
            self.processor = self.processor_class()
            self.processor.init_processor(self)
            self.processor.process_job(job)
        except Exception as e:
            msg = _('[%(worker_tag)s] Error processing job: %(job)s')
            LOG.exception(msg % {'worker_tag': self.get_worker_tag(),
                                 'job': job['id']})
            self.update_job(job['id'], 'ERROR', error_message=unicode(e))
        finally:
            if self.processor is not None:
                self.processor.cleanup_processor()
            self.processor = None

    def _run_loop(self, run_once=False, poll_once=False):
        self.init_worker()
        while self.running:
            time_before = time.time()

            if self._can_accept_job():
                job = self._poll_for_next_job(poll_once)
                if job:
                    try:
                        self.process_job(job)
                    except Exception as e:
                        LOG.exception(e)

            time_after = time.time()

            # Ensure that we wait at least job_poll_interval between jobs
            time_delta = time_after - time_before
            job_poll_interval = get_config_value("job_poll_interval")
            if time_delta < job_poll_interval:
                time.sleep(job_poll_interval - time_delta)

            if run_once:
                self.running = False

        LOG.info(_('[%s] Worker is shutting down') % self.get_worker_tag())
        self._on_shutdown()
        self._unregister_worker()

    def _register_worker(self):
        LOG.info(_('[%(worker_tag)s] Registering worker with pid %(pid)s')
                 % {'worker_tag': self.get_worker_tag(),
                    'pid': str(self.parent_pid)})
        while self.running:
            worker = None
            with utils.log_warning_and_dismiss_exception(LOG):
                worker = self.client.create_worker(self.host, self.parent_pid)

            if worker:
                self.worker_id = worker['id']
                msg = (_('[%s] Worker has been registered')
                       % self.get_worker_tag())
                LOG.info(msg)
                return self.worker_id

            time.sleep(get_config_value("job_poll_interval"))

    def _unregister_worker(self):
        LOG.info(_('[%s] Unregistering worker.') % self.get_worker_tag())
        with utils.log_warning_and_dismiss_exception(LOG):
            self.client.delete_worker(self.worker_id)

    def _poll_for_next_job(self, poll_once=False):
        job = None

        while job is None and self.running:
            time.sleep(get_config_value("job_poll_interval"))
            LOG.debug(_("[%s] Attempting to get next job from API")
                      % self.get_worker_tag())
            job = None
            with utils.log_warning_and_dismiss_exception(LOG):
                job = self.client.get_next_job(
                    self.worker_id, get_config_value("action_type"))['job']

            if poll_once:
                break

        return job

    def get_qonos_client(self):
        return self.client

    def update_job(self, job_id, status, timeout=None, error_message=None):
        msg = (_('[%(worker_tag)s] Updating job [%(job_id)s] '
                 'Status: %(status)s') %
               {'worker_tag': self.get_worker_tag(),
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
            LOG.exception(_("[%s] Failed to update job status.")
                          % self.get_worker_tag())

    def update_job_metadata(self, job_id, metadata):
        return self.client.update_job_metadata(job_id, metadata)


class SingleProcessWorker(WorkerBase):
    def __init__(self, client_factory, processor_class=None):
        super(SingleProcessWorker, self).__init__(client_factory,
                                                  processor_class)

    def process_job(self, job):
        LOG.debug(_('[%(worker_tag)s] Processing job: %(job)s')
                  % {'worker_tag': self.get_worker_tag(),
                     'job': str(job)})
        self._process_job(job)

    def _on_terminate(self, signum):
        if self.processor is not None:
            self.processor.stop_processor()

    def _can_accept_job(self):
        return True


class MultiChildWorker(WorkerBase):
    def __init__(self, client_factory, processor_class=None):
        super(MultiChildWorker, self).__init__(client_factory, processor_class)
        self.pid = None
        self.child_pids = set()

    def process_job(self, job):
        LOG.debug(_('[%(worker_tag)s] Processing job: %(job)s')
                  % {'worker_tag': self.get_worker_tag(),
                     'job': str(job)})

        child_pid = os.fork()
        if child_pid == 0:
            self.pid = os.getpid()
            self._child_process_main(job)
        else:
            job_id = job['id']
            self.child_pids.add((child_pid, job_id))

            LOG.debug(_("[%(worker_tag)s] Forked %(child_pid)s "
                        "for processing job %(job_id)s") %
                      {'worker_tag': self.get_worker_tag(),
                       'child_pid': child_pid,
                       'job_id': job_id})

    def get_worker_tag(self):
        """
        Return a string uniquely identifying this worker for logging.
        """
        tag = super(MultiChildWorker, self).get_worker_tag()
        if self.pid is not None:
            tag += ' C:%s' % self.pid

        return tag

    def _can_reload_configuration(self):
        return self.pid is None

    def _on_terminate(self, signum):
        if self.pid is not None and self.processor is not None:
            self.processor.stop_processor()

    def _on_shutdown(self):
        if self.pid is None:
            for child in self.child_pids:
                os.kill(child[0], signal.SIGTERM)

            count = self._check_children()
            LOG.info(_('[%(worker_tag)s] Waiting on children to shutdown: '
                       '%(children)d remaining')
                     % {'worker_tag': self.get_worker_tag(),
                        'children': count})

            old_count = count
            while count > 0:
                count = self._check_children()
                if old_count != count:
                    LOG.info(_('[%(worker_tag)s] Waiting on children to '
                               'shutdown: %(children)d remaining')
                             % {'worker_tag': self.get_worker_tag(),
                                'children': count})
                    old_count = count
            LOG.info(_('[%(worker_tag)s] All child processes have shutdown')
                     % {'worker_tag': self.get_worker_tag(),
                        'children': count})

    def _can_accept_job(self):
        return self._check_children() < get_config_value("max_child_processes")

    def _parse_status(self, stat_tuple):

        sig = 0
        status = 0
        if os.WIFSIGNALED(stat_tuple):
            sig = os.WTERMSIG(stat_tuple)

        if os.WIFEXITED(stat_tuple):
            status = os.WEXITSTATUS(stat_tuple)
        return status, sig

    def _check_children(self):
        done = set()
        for child in self.child_pids:
            pid = child[0]
            job_id = child[1]
            p, child_info = os.waitpid(pid, os.WNOHANG)
            if p != 0:
                if child_info == 0:
                    LOG.debug(_("[%(worker_tag)s] Normal end of processing "
                                "of job [%(job_id)s] by forked child "
                                "[%(child_pid)s]") %
                              {'worker_tag': self.get_worker_tag(),
                               'job_id': job_id,
                               'child_pid': p})
                else:
                    child_status, child_sig = self._parse_status(child_info)
                    LOG.debug(_("[%(worker_tag)s] Abnormal end of processing "
                                "of job [%(job_id)s] by forked child "
                                "[%(child_pid)s] due to signal %(signal)d"
                                " and exit status %(status)d") %
                              {'worker_tag': self.get_worker_tag(),
                               'job_id': job_id,
                               'child_pid': p,
                               'signal': child_sig,
                               'status': child_status})
                done.add((pid, job_id))

        if len(done) > 0:
            self.child_pids.difference_update(done)

        return len(self.child_pids)

    def _child_process_main(self, job):
        """This is the entry point of the newly spawned child process."""

        self._process_job(job)

        # os._exit() is the way to exit from childs after a fork(), in
        # constrast to the regular sys.exit()
        os._exit(0)


class JobProcessor(object):
    def __init__(self):
        self.worker = None
        self._stopping = False

    def get_qonos_client(self):
        return self.worker.get_qonos_client()

    def get_worker_tag(self):
        if self.worker is None:
            return '<Uninitialized>'

        return self.worker.get_worker_tag()

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
