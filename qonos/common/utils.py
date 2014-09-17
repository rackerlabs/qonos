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

import contextlib
import datetime
import logging as pylog
import sys

from croniter.croniter import croniter
from oslo.config import cfg

from qonos.common import exception as exc
from qonos.common import timeutils
from qonos.openstack.common.gettextutils import _
import qonos.openstack.common.log as logging
from qonos.openstack.common.notifier import api as notifier_api

LOG = logging.getLogger(__name__)


CONF = cfg.CONF
CONF.import_opt('host', 'qonos.netconf')


def generate_notification(context, event_type, payload, level='INFO'):
    publisher_id = notifier_api.publisher_id('qonos', CONF.host)
    notifier_api.notify(context, publisher_id, event_type, level, payload)


def serialize_datetimes(data):
    """Serializes datetimes to strings in the top level values of a dict."""
    for (k, v) in data.iteritems():
        if isinstance(v, datetime.datetime):
            data[k] = timeutils.isotime(v)
        elif isinstance(v, list):
            for item in v:
                serialize_datetimes(item)
        elif isinstance(v, dict):
            serialize_datetimes(v)


def cron_string_to_next_datetime(minute="*", hour="*", day_of_month="*",
                                 month="*", day_of_week="*", start_time=None):
    start_time = start_time or timeutils.utcnow()
    cron_string = ("%s %s %s %s %s" %
                  (_default_if_none(minute, '*'),
                   _default_if_none(hour, '*'),
                   _default_if_none(day_of_month, '*'),
                   _default_if_none(month, '*'),
                   _default_if_none(day_of_week, '*')))
    iter = croniter(cron_string, start_time)
    return iter.get_next(datetime.datetime)


def _default_if_none(value, default):
    if value is None:
        return default
    else:
        return value


def _validate_limit(limit):
    try:
        limit = int(limit)
    except ValueError:
        msg = _("limit param must be an integer")
        raise exc.Invalid(message=msg)
    if limit <= 0:
        msg = _("limit param must be positive")
        raise exc.Invalid(message=msg)
    return limit


def get_pagination_limit(params):
        limit = params.get('limit') or CONF.limit_param_default
        limit = _validate_limit(limit)
        limit = min(CONF.api_limit_max, limit)
        params['limit'] = limit
        return params


def get_qonos_open_file_log_handlers():
    """Returns a list of all open file log handlers."""
    open_files = []
    for handler in pylog.getLogger('qonos').handlers:
        if (hasattr(handler, 'stream') and
                hasattr(handler.stream, 'fileno')):
            open_files.append(handler.stream)
    return open_files


@contextlib.contextmanager
def log_warning_and_dismiss_exception(logger=LOG):
    try:
        yield
    except Exception as ex:
        name, value, tb = sys.exc_info()
        msg = '%(name)s: %(message)s'
        logger.warn(msg % {"name": name.__name__, "message": value})


class LazyPluggable(object):
    """A pluggable backend loaded lazily based on some value."""

    def __init__(self, pivot, config_group=None, **backends):
        self.__backends = backends
        self.__pivot = pivot
        self.__backend = None
        self.__config_group = config_group

    def __get_backend(self):
        if not self.__backend:
            if self.__config_group is None:
                backend_name = CONF[self.__pivot]
            else:
                backend_name = CONF[self.__config_group][self.__pivot]
            if backend_name not in self.__backends:
                msg = _('Invalid backend: %s') % backend_name
                raise exc.QonosException(msg)

            backend = self.__backends[backend_name]
            if isinstance(backend, tuple):
                name = backend[0]
                fromlist = backend[1]
            else:
                name = backend
                fromlist = backend

            self.__backend = __import__(name, None, None, fromlist)
        return self.__backend

    def __getattr__(self, key):
        backend = self.__get_backend()
        return getattr(backend, key)
