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
from qonos.common import wsgi

SERVER_UUID1 = 'ba3f1c5d-89a0-34c1-b44d-ef78d46b90a3'

TENANT1 = '6838eb7b-6ded-434a-882c-b344c77fe8df'
TENANT2 = '2c014f32-5e5b-476d-8fcb-4bd706021f81'
TENANT3 = 'c210f432-5e5b-46d7-8fcb-4bd70012f81'
TENANT4 = '014cf322-5e5b-746d-8cfb-4d706b012f81'

SCHEDULE_UUID1 = '34376f68-f84c-4dfc-a4e7-1b76df6b5c04'
SCHEDULE_UUID2 = '390fd76f-2b9d-4519-9623-31539fb8836f'
SCHEDULE_UUID3 = 'a3491c56-9d38-4a4e-8673-198da85cf778'
SCHEDULE_UUID4 = 'b29bbc05-9dbd-4e23-bbeb-ed52c479c8b6'
SCHEDULE_UUID5 = '4aacce32-0c8a-4205-a2e9-7ebf661a712e'

JOB_UUID1 = '1e37995b-d8ef-4696-8c6b-e263e3778553'
JOB_UUID2 = '96c2c9b9-5c6e-49ac-96a8-82159124c7a1'
JOB_UUID3 = '97652a8a-85ce-404c-b05b-ab26508354c6'
JOB_UUID4 = 'fea36fca-7d4f-434d-ae51-aed0876997e3'
JOB_UUID5 = '410f912b-e6d6-415e-8fe2-3c396ae29e58'
JOB_UUID6 = '410f912b-e6d6-415e-8fe2-3c396ae29e59'

WORKER_UUID1 = '2c3d7e18-a68b-4520-941f-5dda6ae1515e'
WORKER_UUID2 = 'a9f26fd4-d26e-4f3a-b0db-3bd3678373de'
WORKER_UUID3 = 'c531a31a-7859-4664-ac6d-f612aa0e0f7c'
WORKER_UUID4 = 'ee8ddc95-59c3-4d82-befb-2e56d5a735bf'
WORKER_UUID5 = 'dcbed618-b6db-4e29-a9ce-b8d6c04ba3f2'


def get_fake_request(path='', method='GET'):
    req = wsgi.Request.blank(path)
    req.method = method
    return req


def get_schedule(id=None, tenant=TENANT1, job_type=None, schedule=None,
                 metadata=None):
    schedule = {'schedule': {
        'id': id,
        'tenant': tenant,
        'job_type': job_type,
        'schedule': schedule,
        'metadata': metadata
    }}
    return schedule


def get_job(id=None, schedule_id=SCHEDULE_UUID1, status=None):
    job = {'job': {
        'id': id,
        'schedule_id': schedule_id,
        'status': status
    }}
    return job
