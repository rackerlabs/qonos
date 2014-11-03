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

from qonos.common import exception


def validate_schedule_values(values):
    keys = ['action', 'tenant']
    _validate_values('Job', values, keys)


def validate_job_values(values):
    keys = ['action', 'tenant']
    _validate_values('Job', values, keys)


def _validate_values(object_name, values, keys):
    missing_values = []
    for key in keys:
        _validate_value(values, key, missing_values)

    if missing_values:
        raise exception.MissingValue(
            '[%s] Values for %s must be provided' %
            (object_name, missing_values))


def _validate_value(values, key, missing_values):
    if key not in values:
        missing_values.append(key)
