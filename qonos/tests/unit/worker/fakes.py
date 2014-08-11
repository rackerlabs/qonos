# Copyright 2013 Rackspace
# All Rights Reserved.
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
"""
Fakes For Worker tests.
"""

import datetime

from qonos.common import timeutils

WORKER_ID = '11111111-1111-1111-1111-11111111'
JOB_ID = '22222222-2222-2222-2222-22222222'
SCHEDULE_ID = '33333333-3333-3333-3333-33333333'
TENANT = '44444444-4444-4444-4444-44444444'
INSTANCE_ID = '55555555-5555-5555-5555-55555555'

BASE_TIME_T = timeutils.utcnow()
BASE_TIME = timeutils.strtime(at=BASE_TIME_T)
TIMEOUT = timeutils.strtime(BASE_TIME_T + datetime.timedelta(hours=1))
HARD_TIMEOUT = timeutils.strtime(BASE_TIME_T + datetime.timedelta(hours=2))

JOB = {
    'job': {
        'id': JOB_ID,
        'created_at': BASE_TIME,
        'modified_at': BASE_TIME,
        'schedule_id': SCHEDULE_ID,
        'tenant': TENANT,
        'worker_id': WORKER_ID,
        'status': 'QUEUED',
        'action': 'snapshot',
        'retry_count': 1,
        'timeout': TIMEOUT,
        'hard_timeout': HARD_TIMEOUT,
        'metadata': {
            'instance_id': INSTANCE_ID,
            },
    }
}

JOB_NONE = {
    'job': None
}

WORKER_HOST = 'snapshotters'
WORKER_NAME = 'snapshot_1'

WORKER = {
    'id': WORKER_ID,
    'created_at': BASE_TIME,
    'modified_at': BASE_TIME,
    'host': WORKER_HOST,
}
