import time

from qonos.worker import worker
from qonos.common import timeutils
import qonos.openstack.common.log as logging


LOG = logging.getLogger(__name__)


class DummyProcessor(worker.JobProcessor):
    def __init__(self):
        super(DummyProcessor, self).__init__()
        LOG.info('[%s] Created processor' % self.get_worker_tag())
        self.current_job = None

    def init_processor(self, worker, nova_client_factory=None):
        LOG.info('[%s] Initialized processor' % self.get_worker_tag())
        super(DummyProcessor, self).init_processor(worker)

    def process_job(self, job):
        self.current_job = job
        LOG.info('[%s] Started processing job: %s' % (self.get_worker_tag(),
                                                      job['id']))
        start = timeutils.utcnow()
        self.update_job(job['id'], 'PROCESSING')
        self.update_job_metadata(job['id'], {'started': str(start)})

        t = 0
        wait = 5
        while (t * wait) < 30 and not self.stopping:
            LOG.info('[%s] Job: %s Iteration: %d' % (self.get_worker_tag(),
                                                     job['id'], t))
            key = 'update_%d' % t
            self.update_job_metadata(job['id'], {key: str(timeutils.utcnow())})
            time.sleep(wait)
            t += 1

        if not self.stopping:
            LOG.info('[%s] Job: %s Completed at %s' % (self.get_worker_tag(),
                                                       job['id'],
                                                       str(timeutils.utcnow())))
            self.update_job_metadata(job['id'],
                                     {'finished': str(timeutils.utcnow())})
            self.update_job(job['id'], 'DONE')
        else:
            LOG.info('[%s] Job: %s Stopped at %s' % (self.get_worker_tag(),
                                                     job['id'],
                                                     str(timeutils.utcnow())))
            self.update_job(job['id'], 'ERROR')

    def get_worker_tag(self):
        job_tag = ' J:<None>'
        if self.current_job is not None:
            job_tag = ' J:' + self.current_job['id'][:8]
        return super(DummyProcessor, self).get_worker_tag() + job_tag


