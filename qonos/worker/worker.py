from qonos.openstack.common import cfg
from qonos.openstack.common.gettextutils import _
import qonos.openstack.common.log as logging

LOG = logging.getLogger(__name__)

#worker_opts = [
#    cfg.StrOpt('api_endpoint', default='localhost'),
#    cfg.IntOpt('api_port', default=8080),
#]

#CONF = cfg.CONF
#CONF.register_opts(worker_opts, group='worker')


class Worker(object):
    def __init__(self, client_factory):
        print (_('Starting qonos worker %s') % self.__class__.__name__)
