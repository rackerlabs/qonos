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

import datetime

from qonos.api import api
from qonos.common import exception
from qonos.common import timeutils
from qonos.common import utils
from qonos.openstack.common.gettextutils import _

CONF = api.CONF


def serialize_metadata(metadata):
    to_return = {}
    for item in metadata:
        to_return[item['key']] = item['value']
    return to_return


def deserialize_metadata(metadata):
    to_return = []
    for key, value in metadata.iteritems():
        dict_entry = {}
        if len(key.strip()):
            dict_entry['key'] = key
            dict_entry['value'] = value
            to_return.append(dict_entry)
        else:
            msg = _("Metadata value '%s' is missing key") % value
            raise exception.MissingValue(message=unicode(msg))

    return to_return


def check_read_only_properties(values):
    _read_only_properties = ['created_at', 'updated_at', 'last_scheduled']
    bad_keys = []
    for key in values.keys():
        if key in _read_only_properties:
            bad_keys.append(key)

    if bad_keys:
        msg = _("Cannot update the following read-only attributes: %s") \
            % ', '.join(bad_keys)
        raise exception.Forbidden(message=unicode(msg))

    return values


def serialize_schedule_metadata(schedule):
    metadata = schedule.pop('schedule_metadata')
    schedule['metadata'] = serialize_metadata(metadata)


def deserialize_schedule_metadata(schedule):
    if 'metadata' in schedule:
        metadata = schedule.pop('metadata')
        schedule['schedule_metadata'] = deserialize_metadata(metadata)


def serialize_job_metadata(job):
    metadata = job.pop('job_metadata')
    job['metadata'] = serialize_metadata(metadata)


def deserialize_job_metadata(job):
    if 'metadata' in job:
        metadata = job.pop('metadata')
        job['job_metadata'] = deserialize_metadata(metadata)


def schedule_to_next_run(schedule, start_time=None):
    start_time = start_time or timeutils.utcnow()
    minute = schedule.get('minute', '*')
    hour = schedule.get('hour', '*')
    day_of_month = schedule.get('day_of_month', '*')
    month = schedule.get('month', '*')
    day_of_week = schedule.get('day_of_week', '*')
    return utils.cron_string_to_next_datetime(minute, hour, day_of_month,
                                              month, day_of_week,
                                              start_time)


def get_new_timeout_by_action(action):
    now = timeutils.utcnow()

    group = 'action_' + action
    if group not in CONF:
        group = 'action_default'
    job_timeout_seconds = CONF.get(group).timeout_seconds
    return now + datetime.timedelta(seconds=job_timeout_seconds)
