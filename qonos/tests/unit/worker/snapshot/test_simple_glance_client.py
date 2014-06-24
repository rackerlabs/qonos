#    Copyright 2014 Rackspace
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


import mox

from qonos.tests import utils as test_utils
from qonos.worker.snapshot import simple_glance_client


class TestSnapshotProcessor(test_utils.BaseTestCase):
    def setUp(self):
        super(TestSnapshotProcessor, self).setUp()
        self.mox = mox.Mox()
        self.glance_client = self.mox.CreateMockAnything()
        self.images = self.mox.CreateMockAnything()
        self.glance_client.images = self.images

    def tearDown(self):
        super(TestSnapshotProcessor, self).tearDown()
        self.glance_client = None

    def test_get_client_default_version(self):
        exp_version = 1
        exp_endpoint = "http://endpoint"
        exp_token = "my_token"
        client = simple_glance_client.GlanceClient(exp_endpoint, exp_token)

        def fake_create_client(version, endpoint, token):
            self.assertEqual(exp_version, version)
            self.assertEqual(exp_endpoint, endpoint)
            self.assertEqual(exp_token, token)
            return self.glance_client

        self.stubs.Set(client, '_create_client', fake_create_client)
        client._create_client(exp_version, exp_endpoint, exp_token)

    def test_get_client_given_version(self):
        exp_version = 2
        exp_endpoint = "http://endpoint"
        exp_token = "my_token"
        client = simple_glance_client.GlanceClient(exp_endpoint, exp_token,
                                                   exp_version)

        def fake_create_client(version, endpoint, token):
            self.assertEqual(exp_version, version)
            self.assertEqual(exp_endpoint, endpoint)
            self.assertEqual(exp_token, token)
            return self.glance_client

        self.stubs.Set(client, '_create_client', fake_create_client)
        client._create_client(exp_version, exp_endpoint, exp_token)

    def _create_expected_si_filter(self, instance_id):
        return {
            "org.openstack__1__created_by": "scheduled_images_service",
            "instance_uuid": instance_id
        }

    def test_get_si_filter(self):
        instance_id = "my_instance"
        expected = self._create_expected_si_filter(instance_id)
        client = simple_glance_client.GlanceClient(None, None)
        actual = client._get_si_filter(instance_id)

        self.assertEqual(expected, actual)

    def test_get_image(self):
        exp_endpoint = "http://endpoint"
        exp_token = "my_token"
        exp_image_id = "my_image"
        client = simple_glance_client.GlanceClient(exp_endpoint, exp_token)

        self.images.get(exp_image_id)
        self.mox.ReplayAll()

        def fake_create_client(version, endpoint, token):
            return self.glance_client

        self.stubs.Set(client, '_create_client', fake_create_client)

        client.get_image(exp_image_id)

        self.mox.VerifyAll()

    def test_delete_image(self):
        exp_endpoint = "http://endpoint"
        exp_token = "my_token"
        exp_image_id = "my_image"
        client = simple_glance_client.GlanceClient(exp_endpoint, exp_token)

        self.images.delete(exp_image_id)
        self.mox.ReplayAll()

        def fake_create_client(version, endpoint, token):
            return self.glance_client

        self.stubs.Set(client, '_create_client', fake_create_client)

        client.delete_image(exp_image_id)

        self.mox.VerifyAll()

    def test_v1_get_scheduled_images_by_instance(self):
        exp_endpoint = "http://endpoint"
        exp_token = "my_token"
        exp_instance_id = "my_instance"
        client = simple_glance_client.GlanceClient(exp_endpoint, exp_token)

        si_filter = self._create_expected_si_filter(exp_instance_id)
        filters = {
            "properties": si_filter
        }

        self.images.list(filters=filters)
        self.mox.ReplayAll()

        def fake_create_client(version, endpoint, token):
            return self.glance_client

        self.stubs.Set(client, '_create_client', fake_create_client)

        client.get_scheduled_images_by_instance(exp_instance_id)

        self.mox.VerifyAll()

    def test_v2_get_scheduled_images_by_instance(self):
        exp_version = 2
        exp_endpoint = "http://endpoint"
        exp_token = "my_token"
        exp_instance_id = "my_instance"
        client = simple_glance_client.GlanceClient(exp_endpoint, exp_token,
                                                   version=exp_version)

        filters = self._create_expected_si_filter(exp_instance_id)

        self.images.list(filters=filters)
        self.mox.ReplayAll()

        def fake_create_client(version, endpoint, token):
            return self.glance_client

        self.stubs.Set(client, '_create_client', fake_create_client)

        client.get_scheduled_images_by_instance(exp_instance_id)

        self.mox.VerifyAll()
