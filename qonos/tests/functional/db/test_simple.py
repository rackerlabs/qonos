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

import qonos.db.simple.api
from qonos.tests.functional.db import base
from qonos.tests import utils


def setUpModule():
    """Stub in get_db and reset_db for testing the simple db api."""
    base.db_api = qonos.db.simple.api


def tearDownModule():
    """Reset get_db and reset_db for cleanliness."""
    base.db_api = None


# NOTE(ameade): Pull in cross driver db tests
thismodule = sys.modules[__name__]
utils.import_test_cases(thismodule, base, suffix="_Simple_DB")
