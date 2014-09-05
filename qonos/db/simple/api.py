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

import copy
import datetime
import operator
import uuid

from operator import itemgetter
from qonos.common import exception
from qonos.common import timeutils
import qonos.db.db_utils as db_utils
from qonos.openstack.common.gettextutils import _


DATA = {
    'schedules': {},
    'schedule_metadata': {},
    'jobs': {},
    'job_metadata': {},
    'workers': {},
    'job_faults': {},
}


def configure_db():
    pass


def reset():
    global DATA
    for k in DATA:
        DATA[k] = {}


def _gen_base_attributes(item_id=None):
    values = {}
    if item_id is None:
        values['id'] = str(uuid.uuid4())
    values['created_at'] = timeutils.utcnow()
    values['updated_at'] = timeutils.utcnow()
    return copy.deepcopy(values)


def _schedule_create(values):
    global DATA
    DATA['schedules'][values['id']] = values
    _schedule_meta_init(values['id'])
    return copy.deepcopy(values)


def _do_pagination(items, marker, limit):
    """
    This method mimics the behavior of sqlalchemy paginate_query.
    It takes items and pagination parameters - 'limit' and 'marker'
    to filter out the items to be returned. Items are sorted in
    lexicographical order based on the sort key - 'id'.
    """
    items = sorted(items, key=itemgetter('id'))
    start = 0
    end = -1
    if marker is None:
        start = 0
    else:
        for i, item in enumerate(items):
            if item['id'] == marker:
                start = i + 1
                break
        else:
            msg = _('Marker %s not found') % marker
            raise exception.NotFound(explanation=msg)

    end = start + limit if limit is not None else None
    return items[start:end]


def schedule_get_all(filter_args={}):
    SCHEDULE_BASE_FILTERS = ['next_run_after', 'next_run_before',
                             'tenant', 'limit', 'marker']
    schedules = copy.deepcopy(DATA['schedules'].values())
    schedules_mutate = copy.deepcopy(DATA['schedules'].values())

    for schedule in schedules:
        schedule['schedule_metadata'] =\
            copy.deepcopy(schedule_meta_get_all(schedule['id']))

    schedules_mutate = copy.deepcopy(schedules)

    if 'next_run_before' in filter_args:
        for schedule in schedules:
            if not schedule['next_run'] <= filter_args['next_run_before']:
                if schedule in schedules_mutate:
                    del schedules_mutate[schedules_mutate.index(schedule)]
        filter_args.pop('next_run_before')

    if 'next_run_after' in filter_args:
        for schedule in schedules:
            if not schedule['next_run'] >= filter_args['next_run_after']:
                if schedule in schedules_mutate:
                    del schedules_mutate[schedules_mutate.index(schedule)]
        filter_args.pop('next_run_after')

    if filter_args.get('tenant') is not None:
        for schedule in schedules:
            if schedule['tenant'] != filter_args['tenant']:
                if schedule in schedules_mutate:
                    del schedules_mutate[schedules_mutate.index(schedule)]
        filter_args.pop('tenant')

    if filter_args.get('action') is not None:
        for schedule in schedules:
            if schedule['action'] != filter_args['action']:
                if schedule in schedules_mutate:
                    del schedules_mutate[schedules_mutate.index(schedule)]
        filter_args.pop('action')

    for filter_key in filter_args.keys():
        if filter_key not in SCHEDULE_BASE_FILTERS:
            filter_value = filter_args[filter_key]
            for schedule in schedules:
                if schedule['schedule_metadata']:
                    for schedule_metadata in schedule['schedule_metadata']:
                        if not(schedule_metadata['key'] == filter_key and
                               schedule_metadata['value'] == filter_value):
                            try:
                                schedule_mutated = (
                                        schedules_mutate.index(schedule))
                                del schedules_mutate[schedule_mutated]
                            except Exception:
                                pass
                            break
                else:
                    if schedule in schedules_mutate:
                        del schedules_mutate[schedules_mutate.index(schedule)]

    marker = filter_args.get('marker')
    limit = filter_args.get('limit')
    schedules_mutate = _do_pagination(schedules_mutate, marker, limit)
    return schedules_mutate


def schedule_get_by_id(schedule_id):
    if schedule_id not in DATA['schedules']:
        raise exception.NotFound()
    schedule = copy.deepcopy(DATA['schedules'][schedule_id])
    schedule['schedule_metadata'] = \
        copy.deepcopy(schedule_meta_get_all(schedule_id))
    return schedule


def schedule_create(schedule_values):
    db_utils.validate_schedule_values(schedule_values)
    values = copy.deepcopy(schedule_values)
    schedule = {}

    metadata = []
    if 'schedule_metadata' in values:
        metadata = values['schedule_metadata']
        del values['schedule_metadata']

    schedule.update(values)
    item_id = values.get('id')
    schedule.update(_gen_base_attributes(item_id=item_id))
    schedule = _schedule_create(schedule)

    for metadatum in metadata:
        schedule_meta_create(schedule['id'], metadatum)

    return schedule_get_by_id(schedule['id'])


def schedule_update(schedule_id, schedule_values):
    global DATA
    values = schedule_values.copy()

    if schedule_id not in DATA['schedules']:
        raise exception.NotFound()

    metadata = None
    if 'schedule_metadata' in values:
        metadata = values['schedule_metadata']
        del values['schedule_metadata']

    if len(values) > 0:
        schedule = DATA['schedules'][schedule_id]
        schedule['updated_at'] = timeutils.utcnow()
        schedule.update(values)

    if metadata is not None:
        DATA['schedule_metadata'][schedule_id] = {}
        for metadatum in metadata:
            schedule_meta_create(schedule_id, metadatum)

    return schedule_get_by_id(schedule_id)


def schedule_test_and_set_next_run(schedule_id, expected_next_run, next_run):
    global DATA

    schedule = DATA['schedules'].get(schedule_id)

    if not schedule:
        raise exception.NotFound()

    if expected_next_run:
        expected_next_run = expected_next_run.replace(tzinfo=None)
        current_next_run = schedule.get('next_run')
        if current_next_run:
            current_next_run = current_next_run.replace(tzinfo=None)
        if expected_next_run != current_next_run:
            raise exception.NotFound()
    if next_run:
        next_run = next_run.replace(tzinfo=None)
    schedule['next_run'] = next_run


def schedule_delete(schedule_id):
    global DATA
    if schedule_id not in DATA['schedules']:
        raise exception.NotFound()
    del DATA['schedules'][schedule_id]


def _schedule_meta_init(schedule_id):
    if DATA['schedule_metadata'].get(schedule_id) is None:
        DATA['schedule_metadata'][schedule_id] = {}


def schedule_meta_create(schedule_id, values):
    global DATA
    if DATA['schedules'].get(schedule_id) is None:
        msg = _('Schedule %s could not be found') % schedule_id
        raise exception.NotFound(message=msg)

    _schedule_meta_init(schedule_id)

    try:
        _check_meta_exists(schedule_id, values['key'])
    except exception.NotFound:
        pass
    else:
        raise exception.Duplicate()

    meta = {}
    values['schedule_id'] = schedule_id
    meta.update(values)
    meta.update(_gen_base_attributes())
    DATA['schedule_metadata'][schedule_id][values['key']] = meta
    return copy.deepcopy(meta)


def _check_schedule_exists(schedule_id):
    if DATA['schedules'].get(schedule_id) is None:
        msg = _('Schedule %s could not be found') % schedule_id
        raise exception.NotFound(message=msg)


def _check_meta_exists(schedule_id, key):
    _check_schedule_exists(schedule_id)

    if (DATA['schedule_metadata'].get(schedule_id) is None or
            DATA['schedule_metadata'][schedule_id].get(key) is None):
        msg = (_('Meta %(key)s could not be found '
                 'for Schedule %(schedule_id)s ') %
               {'key': key, 'schedule_id': schedule_id})
        raise exception.NotFound(message=msg)


def schedule_meta_get_all(schedule_id):
    _check_schedule_exists(schedule_id)
    _schedule_meta_init(schedule_id)

    return DATA['schedule_metadata'][schedule_id].values()


def schedule_metadata_update(schedule_id, values):
    global DATA
    if DATA['schedules'].get(schedule_id) is None:
        msg = _('Schedule %s could not be found') % schedule_id
        raise exception.NotFound(message=msg)

    DATA['schedule_metadata'][schedule_id] = {}
    for metadatum in values:
        schedule_meta_create(schedule_id, metadatum)

    return copy.deepcopy(DATA['schedule_metadata'][schedule_id].values())


def _delete_schedule_meta(schedule_id, key):
    del DATA['schedule_metadata'][schedule_id][key]


def schedule_meta_delete(schedule_id, key):
    _check_meta_exists(schedule_id, key)
    _delete_schedule_meta(schedule_id, key)


def worker_get_all(params={}):
    workers = copy.deepcopy(DATA['workers'].values())
    marker = params.get('marker')
    limit = params.get('limit')
    workers = _do_pagination(workers, marker, limit)
    return workers


def worker_get_by_id(worker_id):
    if worker_id not in DATA['workers']:
        raise exception.NotFound()
    return copy.deepcopy(DATA['workers'][worker_id])


def worker_create(values):
    global DATA
    worker_values = copy.deepcopy(values)
    if 'process_id' not in worker_values:
        worker_values['process_id'] = None
    worker = {}
    worker.update(worker_values)
    item_id = values.get('id')
    worker.update(_gen_base_attributes(item_id=item_id))
    DATA['workers'][worker['id']] = worker
    return copy.deepcopy(worker)


def worker_delete(worker_id):
    global DATA
    if worker_id not in DATA['workers']:
        raise exception.NotFound()
    del DATA['workers'][worker_id]


def job_create(job_values):
    global DATA
    db_utils.validate_job_values(job_values)
    values = job_values.copy()
    job = {}

    metadata = []
    if 'job_metadata' in values:
        metadata = values['job_metadata']
        del values['job_metadata']

    if not 'retry_count' in values:
        values['retry_count'] = 0
    job['worker_id'] = None
    job['version_id'] = str(uuid.uuid4())

    job.update(values)
    item_id = values.get('id')
    job.update(_gen_base_attributes(item_id=item_id))

    DATA['jobs'][job['id']] = job

    for metadatum in metadata:
        job_meta_create(job['id'], metadatum)

    return job_get_by_id(job['id'])


def job_get_all(params={}):
    jobs = copy.deepcopy(DATA['jobs'].values())
    JOB_BASE_FILTERS = ['schedule_id',
                        'tenant',
                        'action',
                        'worker_id',
                        'status',
                        'timeout',
                        'hard_timeout']

    for key in JOB_BASE_FILTERS:
        if key in params:
            value = params.get(key)
            if type(value) is datetime.datetime:
                value = timeutils.normalize_time(value).replace(microsecond=0)

            for job in reversed(jobs):
                job_value = job.get(key)
                if job_value and type(job_value) is datetime.datetime:
                    job_value = job_value.replace(microsecond=0)
                if not (job_value == value):
                    del jobs[jobs.index(job)]

    for job in jobs:
        job['job_metadata'] =\
            job_meta_get_all_by_job_id(job['id'])

    marker = params.get('marker')
    limit = params.get('limit')
    jobs = _do_pagination(jobs, marker, limit)

    return jobs


def job_get_by_id(job_id):
    if job_id not in DATA['jobs']:
        raise exception.NotFound()

    job = copy.deepcopy(DATA['jobs'][job_id])

    job['job_metadata'] = \
        job_meta_get_all_by_job_id(job_id)

    return job


def job_updated_at_get_by_id(job_id):
    job = job_get_by_id(job_id)
    return job['updated_at']


def job_get_and_assign_next_by_action(action, worker_id, new_timeout):
    """Get the next available job for the given action and assign it
    to the worker for worker_id.
    This must be an atomic action!"""
    job_ref = None
    now = timeutils.utcnow().replace(second=0, microsecond=0)
    jobs = _jobs_get_sorted()
    statuses = ['DONE', 'CANCELLED', 'HARD_TIMED_OUT', 'MAX_RETRIED']
    for job in jobs:
        if job['action'] == action and \
                job['status'] not in statuses and \
                (job['worker_id'] is None or job['timeout'] <= now):
            job_ref = job
            break

    if job_ref is None:
        return None

    job_id = job_ref['id']
    DATA['jobs'][job_id]['worker_id'] = worker_id
    DATA['jobs'][job_id]['timeout'] = new_timeout
    DATA['jobs'][job_id]['retry_count'] = job_ref['retry_count'] + 1
    DATA['jobs'][job_id]['version_id'] = str(uuid.uuid4())
    job = copy.deepcopy(DATA['jobs'][job_id])
    job['job_metadata'] = job_meta_get_all_by_job_id(job_id)

    return job


def _jobs_get_sorted():
    jobs = copy.deepcopy(DATA['jobs'])
    sorted_jobs = []
    for job_id in jobs:
        sorted_jobs.append(jobs[job_id])

    sorted_jobs = sorted(sorted_jobs, key=operator.itemgetter('updated_at'))
    return sorted_jobs


def _jobs_cleanup_hard_timed_out():
    """Find all jobs with hard_timeout values which have passed
    and delete them, logging the timeout / failure as appropriate"""
    now = timeutils.utcnow()
    del_ids = []
    for job_id in DATA['jobs']:
        job = DATA['jobs'][job_id]
        print now, job['hard_timeout']
        print now - job['hard_timeout']
        if (now - job['hard_timeout']) > datetime.timedelta(microseconds=0):
            del_ids.append(job_id)

    for job_id in del_ids:
        job_delete(job_id)
    return len(del_ids)


def job_update(job_id, job_values):
    global DATA
    values = job_values.copy()
    if job_id not in DATA['jobs']:
        raise exception.NotFound()

    metadata = None
    if 'job_metadata' in values:
        metadata = values['job_metadata']
        del values['job_metadata']

    if len(values) > 0:
        job = DATA['jobs'][job_id]
        #NOTE(ameade): This must come before update specified values since
        # we may be trying to manually set updated_at
        job['updated_at'] = timeutils.utcnow()
        job['version_id'] = str(uuid.uuid4())
        job.update(values)

    if metadata is not None:
        DATA['job_metadata'][job_id] = {}
        for metadatum in metadata:
            job_meta_create(job_id, metadatum)

    return job_get_by_id(job_id)


def job_delete(job_id):
    global DATA
    if job_id not in DATA['jobs']:
        raise exception.NotFound()
    del DATA['jobs'][job_id]


def job_meta_create(job_id, values):
    global DATA
    values['job_id'] = job_id
    _check_job_exists(job_id)

    if DATA['job_metadata'].get(job_id) is None:
        DATA['job_metadata'][job_id] = {}

    try:
        _check_job_meta_exists(job_id, values['key'])
    except exception.NotFound:
        pass
    else:
        raise exception.Duplicate()

    meta = {}
    meta.update(values)
    meta.update(_gen_base_attributes())
    DATA['job_metadata'][job_id][values['key']] = meta
    return copy.deepcopy(meta)


def _check_job_exists(job_id):
    if not job_id in DATA['jobs']:
        msg = _('Job %s could not be found') % job_id
        raise exception.NotFound(message=msg)


def _check_job_meta_exists(job_id, key):

    if (DATA['job_metadata'].get(job_id) is None or
            DATA['job_metadata'][job_id].get(key) is None):
        msg = (_('Meta %(key)s could not be found for Job %(job_id)s ') %
               {'key': key, 'job_id': job_id})
        raise exception.NotFound(message=msg)


def job_meta_get_all_by_job_id(job_id):
    _check_job_exists(job_id)

    if job_id not in DATA['job_metadata']:
        DATA['job_metadata'][job_id] = {}

    return copy.deepcopy(DATA['job_metadata'][job_id].values())


def job_metadata_update(job_id, values):
    global DATA
    _check_job_exists(job_id)

    DATA['job_metadata'][job_id] = {}
    for metadatum in values:
        job_meta_create(job_id, metadatum)

    return copy.deepcopy(DATA['job_metadata'][job_id].values())


def _job_faults_get_sorted():
    jobs = copy.deepcopy(DATA['job_faults'])
    sorted_jobs = []
    for job_id in jobs:
        sorted_jobs.append(jobs[job_id])

    sorted_jobs = sorted(sorted_jobs, key=operator.itemgetter('created_at'),
                         reverse=True)
    return sorted_jobs


def job_fault_latest_for_job_id(job_id):
    job_faults = _job_faults_get_sorted()
    for job_fault in job_faults:
        if job_fault['job_id'] == job_id:
            return job_fault
    return None


def job_fault_create(values):
    global DATA
    job_fault = {}
    job_fault.update(values)
    item_id = values.get('id')
    job_fault.update(_gen_base_attributes(item_id=item_id))
    DATA['job_faults'][job_fault['id']] = job_fault
    return copy.deepcopy(job_fault)
