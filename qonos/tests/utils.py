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

import inspect
import stubout
import unittest2

from oslo.config import cfg

from qonos.common import config


CONF = cfg.CONF


class BaseTestCase(unittest2.TestCase):

    def setUp(self):
        super(BaseTestCase, self).setUp()
        # NOTE(ameade): we need config options to be registered
        config.parse_args(args=[])
        self.stubs = stubout.StubOutForTesting()

    def tearDown(self):
        super(BaseTestCase, self).tearDown()
        CONF.reset()
        self.stubs.UnsetAll()

    def config(self, **kw):
        """
        Override some configuration values.

        The keyword arguments are the names of configuration options to
        override and their values.

        If a group argument is supplied, the overrides are applied to
        the specified configuration option group.

        All overrides are automatically cleared at the end of the current
        test by the tearDown() method.
        """
        group = kw.pop('group', None)
        for k, v in kw.iteritems():
            CONF.set_override(k, v, group)

    def assertMetadataInList(self, expected_metadata, actual_metadata):
        for key, value in actual_metadata.iteritems():
            self.assertMetaInList(expected_metadata, {key: value})

    def assertMetaInList(self, metadata, meta):
        found = False
        self.assertEqual(1, len(meta))
        key = meta.keys()[0]
        if key in metadata:
            found = True
            self.assertEqual(metadata[key], meta[key])
        self.assertTrue(found)

    def assertDbMetaInList(self, metadata, meta):
        found = False
        test_meta = {}
        for item in metadata:
            test_meta[item['key']] = item['value']
        found = meta['key'] in test_meta
        if found:
            self.assertEqual(test_meta[meta['key']], meta['value'])
        self.assertTrue(found)


def import_test_cases(target_module, test_module, suffix=""):
    """Adds test cases to target module.

    Adds all testcase classes in test_module to target_module and appends an
    optional suffix.

    :param target_module: module which has an attribute set for each test case
    :param test_module: module containing test cases to copy
    :param suffix: an optional suffix to be added to each test case class name

    """
    for name, obj in inspect.getmembers(test_module):
        if inspect.isclass(obj) and issubclass(obj, BaseTestCase):
            setattr(target_module, name + suffix,
                    type(name + suffix, (obj,), {}))
