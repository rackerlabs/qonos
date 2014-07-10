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

from qonos.openstack.common.gettextutils import _


class QonosException(Exception):
    message = 'An unknown exception occurred'

    def __init__(self, message=None, *args, **kwargs):
        if not message:
            message = self.message
        try:
            message = message % kwargs
        except Exception:
            # at least get the core message out if something happened
            pass
        super(QonosException, self).__init__(_(message))


class NotFound(QonosException):
    message = 'An object with the specified identifier could not be found.'


class Forbidden(QonosException):
    message = 'The action performed is forbidden for given object.'


class Duplicate(QonosException):
    message = 'An object with the specified identifier already exists.'


class MissingValue(QonosException):
    message = 'A required value was not provided'


class Invalid(QonosException):
    message = 'The input provided was invalid.'


class PollingException(QonosException):
    message = 'An error occured when polling.'


class OutOfTimeException(QonosException):
    message = ('Timeout occurred while trying to process job %(job)s in '
               'status %(status)s')


class DatabaseMigrationError(QonosException):
    message = "There was an error migrating the database."
