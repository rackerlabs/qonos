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

import sys

from oslo_config import cfg

from qonos.tests.functional.v1 import base
from qonos.tests import utils as utils

CONF = cfg.CONF


def setUpModule():
    CONF.db_api = 'qonos.db.sqlalchemy.api'


def tearDownModule():
    CONF.db_api = None


module = sys.modules[__name__]
utils.import_test_cases(module, base, suffix="_Sqlalchemy_DB")
