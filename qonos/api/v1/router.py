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

import routes

from qonos.api.v1 import job_metadata
from qonos.api.v1 import jobs
from qonos.api.v1 import schedule_metadata
from qonos.api.v1 import schedules
from qonos.api.v1 import workers
from qonos.common import wsgi


class API(wsgi.Router):

    def __init__(self, mapper):
        schedules_resource = schedules.create_resource()

        mapper.connect('/schedules',
                       controller=schedules_resource,
                       action='list',
                       conditions=dict(method=['GET']))

        mapper.connect('/schedules',
                       controller=schedules_resource,
                       action='create',
                       conditions=dict(method=['POST']))

        mapper.connect('/schedules/{schedule_id}',
                       controller=schedules_resource,
                       action='get',
                       conditions=dict(method=['GET']))

        mapper.connect('/schedules/{schedule_id}',
                       controller=schedules_resource,
                       action='update',
                       conditions=dict(method=['PUT']))

        mapper.connect('/schedules/{schedule_id}',
                       controller=schedules_resource,
                       action='delete',
                       conditions=dict(method=['DELETE']))

        schedule_meta_resource = schedule_metadata.create_resource()

        mapper.connect('/schedules/{schedule_id}/metadata',
                       controller=schedule_meta_resource,
                       action='list',
                       conditions=dict(method=['GET']))

        mapper.connect('/schedules/{schedule_id}/metadata',
                       controller=schedule_meta_resource,
                       action='update',
                       conditions=dict(method=['PUT']))

        jobs_resource = jobs.create_resource()

        mapper.connect('/jobs',
                       controller=jobs_resource,
                       action='list',
                       conditions=dict(method=['GET']))

        mapper.connect('/jobs',
                       controller=jobs_resource,
                       action='create',
                       conditions=dict(method=['POST']))

        mapper.connect('/jobs/{job_id}',
                       controller=jobs_resource,
                       action='get',
                       conditions=dict(method=['GET']))

        mapper.connect('/jobs/{job_id}',
                       controller=jobs_resource,
                       action='delete',
                       conditions=dict(method=['DELETE']))

        mapper.connect('/jobs/{job_id}/status',
                       controller=jobs_resource,
                       action='update_status',
                       conditions=dict(method=['PUT']))

        job_meta_resource = job_metadata.create_resource()

        mapper.connect('/jobs/{job_id}/metadata',
                       controller=job_meta_resource,
                       action='list',
                       conditions=dict(method=['GET']))

        mapper.connect('/jobs/{job_id}/metadata',
                       controller=job_meta_resource,
                       action='update',
                       conditions=dict(method=['PUT']))

        workers_resource = workers.create_resource()

        mapper.connect('/workers',
                       controller=workers_resource,
                       action='list',
                       conditions=dict(method=['GET']))

        mapper.connect('/workers',
                       controller=workers_resource,
                       action='create',
                       conditions=dict(method=['POST']))

        mapper.connect('/workers/{worker_id}',
                       controller=workers_resource,
                       action='get',
                       conditions=dict(method=['GET']))

        mapper.connect('/workers/{worker_id}',
                       controller=workers_resource,
                       action='delete',
                       conditions=dict(method=['DELETE']))

        mapper.connect('/workers/{worker_id}/jobs',
                       controller=workers_resource,
                       action='get_next_job',
                       conditions=dict(method=['POST']))

        super(API, self).__init__(mapper)

    @classmethod
    def factory(cls, global_conf, **local_conf):
        return cls(routes.Mapper())
