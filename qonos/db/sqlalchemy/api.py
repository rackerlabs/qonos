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

"""
Defines interface for DB access
"""

import functools
import inspect
import logging
import time

from oslo_config import cfg
import sqlalchemy
import sqlalchemy.orm as sa_orm
import sqlalchemy.sql as sa_sql

from qonos.common import exception
from qonos.common import timeutils
import qonos.db.db_utils as db_utils
from qonos.db.sqlalchemy import models
from qonos.openstack.common._i18n import _
import qonos.openstack.common.log as os_logging


_ENGINE = None
_MAKER = None
_MAX_RETRIES = None
_RETRY_INTERVAL = None
BASE = models.BASE
sa_logger = None
LOG = os_logging.getLogger(__name__)

db_opts = [
    cfg.IntOpt('sql_idle_timeout', default=3600),
    cfg.IntOpt('sql_max_retries', default=60),
    cfg.IntOpt('sql_retry_interval', default=1),
    cfg.BoolOpt('db_auto_create', default=True),
    cfg.BoolOpt('log_query_times', default=False)
]

CONF = cfg.CONF
CONF.register_opts(db_opts)


def force_dict(func):
    """Ensure returned object is a dict or list of dicts."""

    def convert_list(a_list):
        to_return = []
        for object in a_list:
            if isinstance(object, list):
                to_return.append(convert_list(object))
            else:
                to_return.append(convert_object(object))
        return to_return

    def convert_object(object):
        if (isinstance(object, models.ModelBase) or
                isinstance(object, tuple)):
            to_return = dict(object)
        elif (isinstance(object, dict)):
            to_return = object
        else:
            raise ValueError()

        if 'parent' in to_return:
            del to_return['parent']

        if '_sa_instance_state' in to_return:
            del to_return['_sa_instance_state']

        for key in to_return:
            if isinstance(to_return[key], list):
                to_return[key] = convert_list(to_return[key])
            elif isinstance(to_return[key], models.ModelBase):
                to_return[key] = convert_object(to_return[key])

        return to_return

    def convert_output(output):
        if output is None:
            to_return = None
        elif isinstance(output, list):
            to_return = convert_list(output)
        else:
            to_return = convert_object(output)
        return to_return

    @functools.wraps(func)
    def wrapped(*args, **kwargs):
        output = func(*args, **kwargs)
        return convert_output(output)
    return wrapped


def ping_listener(dbapi_conn, connection_rec, connection_proxy):

    """
    Ensures that MySQL connections checked out of the
    pool are alive.

    Borrowed from:
    http://groups.google.com/group/sqlalchemy/msg/a4ce563d802c929f
    """

    try:
        dbapi_conn.cursor().execute('select 1')
    except dbapi_conn.OperationalError, ex:
        if ex.args[0] in (2006, 2013, 2014, 2045, 2055):
            msg = 'Got mysql server has gone away: %s' % ex
            LOG.warn(msg)
            raise sqlalchemy.exc.DisconnectionError(msg)
        else:
            raise


def configure_db():
    """
    Establish the database, create an engine if needed, and
    register the models.
    """
    global _ENGINE, sa_logger
    LOG.debug("Initializing DB")
    if not _ENGINE:
        _ENGINE = get_engine()

        sa_logger = logging.getLogger('sqlalchemy.engine')
        if CONF.debug:
            sa_logger.setLevel(logging.DEBUG)

        if CONF.db_auto_create:
            LOG.info('auto-creating qonos DB')
            models.register_models(_ENGINE)
        else:
            LOG.info('not auto-creating qonos DB')


def reset():
    models.unregister_models(_ENGINE)
    models.register_models(_ENGINE)


def _before_cursor_execute(conn,
                           cursor,
                           statement,
                           parameters,
                           context,
                           executemany,
                           ):
    stack = inspect.stack()
    try:
        # NOTE(alaski): stack is a list of tuples like (_, filename, _,
        # method_name, _, _) where _ are irrelevant slots. The list is
        # filtered to find the call through sqlalchemy/api.py and then
        # the method_name is pulled from that stack frame.
        db_frames = filter(lambda x: x[1].endswith('sqlalchemy/api.py'), stack)
        method = db_frames[0][3]
    except IndexError:
        method = 'unknown'
    conn.info['query_start_time'] = timeutils.utcnow()
    conn.info['query_method'] = method


def _after_cursor_execute(conn,
                          cursor,
                          statement,
                          parameters,
                          context,
                          executemany,
                          ):
    method = conn.info.get('query_method')
    start_time = conn.info.get('query_start_time')
    if start_time:
        now = timeutils.utcnow()
        total = (now - start_time).total_seconds()
    else:
        total = -1.0
    msg = "Query time for '%s': %f. Query statement: %s"
    LOG.debug(msg % (method, total, statement))


def get_engine():
    global _ENGINE, _MAX_RETRIES, _RETRY_INTERVAL
    if not _ENGINE:
        sql_connection = CONF.sql_connection
        _MAX_RETRIES = CONF.sql_max_retries
        _RETRY_INTERVAL = CONF.sql_retry_interval
        connection_dict = sqlalchemy.engine.url.make_url(sql_connection)
        engine_args = {'pool_recycle': CONF.sql_idle_timeout,
                       'echo': False,
                       'convert_unicode': True
                       }

        try:
            _ENGINE = sqlalchemy.create_engine(sql_connection, **engine_args)

            if 'mysql' in connection_dict.drivername:
                sqlalchemy.event.listen(_ENGINE, 'checkout', ping_listener)

            if CONF.log_query_times:
                sqlalchemy.event.listen(_ENGINE, 'before_cursor_execute',
                                        _before_cursor_execute())
                sqlalchemy.event.listen(_ENGINE, 'after_cursor_execute',
                                        _after_cursor_execute())

            _ENGINE.connect = wrap_db_error(_ENGINE.connect)
            _ENGINE.connect()
        except Exception, err:
            msg = _("Error configuring registry database with supplied "
                    "sql_connection '%(sql_connection)s'. "
                    "Got error:\n%(err)s") % locals()
            LOG.error(msg)
            raise
    return _ENGINE


def get_session(autocommit=True, expire_on_commit=False):
    """Helper method to grab session."""
    global _MAKER
    if not _MAKER:
        assert _ENGINE
        _MAKER = sa_orm.sessionmaker(bind=_ENGINE,
                                     autocommit=autocommit,
                                     expire_on_commit=expire_on_commit)
    return _MAKER()


def is_db_connection_error(args):
    """Return True if error in connecting to db."""
    # NOTE(adam_g): This is currently MySQL specific and needs to be extended
    #               to support Postgres and others.
    conn_err_codes = ('2002', '2003', '2006')
    for err_code in conn_err_codes:
        if args.find(err_code) != -1:
            return True
    return False


def wrap_db_error(f):
    """Retry DB connection. Copied from nova and modified."""
    def _wrap(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except sqlalchemy.exc.OperationalError, e:
            if not is_db_connection_error(e.args[0]):
                raise

            remaining_attempts = _MAX_RETRIES
            while True:
                LOG.warning(_('SQL connection failed. %d attempts left.'),
                            remaining_attempts)
                remaining_attempts -= 1
                time.sleep(_RETRY_INTERVAL)
                try:
                    return f(*args, **kwargs)
                except sqlalchemy.exc.OperationalError, e:
                    if (remaining_attempts == 0 or
                            not is_db_connection_error(e.args[0])):
                        raise
                except sqlalchemy.exc.DBAPIError:
                    raise
        except sqlalchemy.exc.DBAPIError:
            raise
    _wrap.func_name = f.func_name
    return _wrap


# Schedule methods


@force_dict
def schedule_create(schedule_values):
    db_utils.validate_schedule_values(schedule_values)
    # make a copy so we can remove 'schedule_metadata'
    # without affecting the caller
    values = schedule_values.copy()
    metadata = None
    session = get_session()
    schedule_ref = models.Schedule()

    if 'schedule_metadata' in values:
        metadata = values['schedule_metadata']
        _set_schedule_metadata(schedule_ref, metadata)
        del values['schedule_metadata']

    schedule_ref.update(values)
    schedule_ref.save(session=session)

    return _schedule_get_by_id(schedule_ref['id'])


def paginate_query(query, model, sort_keys, limit=None, marker=None):
    """
    Returns a query with sorting and(or) pagination criteria added.

    Pagination works by requiring a unique sort_key, specified by sort_keys.
    (If sort_keys is not unique, then we risk looping through values.)
    We use the last row in the previous page as the 'marker' for pagination.
    So we must return values that follow the passed marker in the order.
    With a single-valued sort_key, this would be easy: sort_key > X.
    With a compound-values sort_key, (k1, k2, k3) we must do this to repeat
    the lexicographical ordering:
    (k1 > X1) or (k1 == X1 && k2 > X2) or (k1 == X1 && k2 == X2 && k3 > X3)

    Typically, the id of the last row is used as the client-facing pagination
    marker, then the actual marker object must be fetched from the db and
    passed in to us as marker.

    :param query: the query object to which we should add paging/sorting
    :param model: the ORM model class
    :param sort_keys: array of attributes by which results should be sorted
    :param limit: maximum number of items to return
    :param marker: the last item of the previous page; we returns the next
                    results after this value.

    :rtype: sqlalchemy.orm.query.Query
    :return: The query with sorting and(or) pagination added.
    """
    # Note(nikhil): Curently pagination does not support sort directions. By
    # default the items are sorted in ascending order.
    for sort_key in sort_keys:
        try:
            sort_key_attr = getattr(model, sort_key)
        except AttributeError:
            raise exception.InvalidSortKey()
        query = query.order_by(sqlalchemy.asc(sort_key_attr))

    if marker is not None:
        marker_values = []
        for sort_key in sort_keys:
            v = getattr(marker, sort_key)
            marker_values.append(v)

    # Note(nikhil): the underlying code only supports asc order of sort_dir
    # at the moment. However, more than one sort_keys could be supplied.
        criteria_list = []
        for i in xrange(0, len(sort_keys)):
            crit_attrs = []
            for j in xrange(0, i):
                model_attr = getattr(model, sort_keys[j])
                crit_attrs.append((model_attr == marker_values[j]))
            model_attr = getattr(model, sort_keys[i])
            crit_attrs.append((model_attr > marker_values[i]))
            criteria = sa_sql.and_(*crit_attrs)
            criteria_list.append(criteria)

        f = sa_sql.or_(*criteria_list)
        query = query.filter(f)

    if limit is not None:
        query = query.limit(limit)

    return query


@force_dict
def schedule_get_all(filter_args={}):
    session = get_session()
    query = session.query(models.Schedule)\
                   .options(sa_orm.joinedload_all(
                            models.Schedule.schedule_metadata))
    SCHEDULE_BASE_FILTERS = ['next_run_after', 'next_run_before', 'tenant',
                             'limit', 'marker', 'action']

    if 'next_run_after' in filter_args:
        query = query.filter(
            models.Schedule.next_run >= filter_args['next_run_after'])
        filter_args.pop('next_run_after')

    if 'next_run_before' in filter_args:
        query = query.filter(
            models.Schedule.next_run <= filter_args['next_run_before'])

    if filter_args.get('tenant') is not None:
        query = query.filter(models.Schedule.tenant ==
                             filter_args['tenant'])

    if filter_args.get('action') is not None:
        query = query.filter(models.Schedule.action ==
                             filter_args['action'])

    for filter_key in filter_args.keys():
        if filter_key not in SCHEDULE_BASE_FILTERS:
            query = query.filter(models.Schedule.schedule_metadata.any(
                                 key=filter_key,
                                 value=filter_args[filter_key]))

    marker_schedule = None
    if filter_args.get('marker') is not None:
        marker_schedule = _schedule_get_by_id(filter_args['marker'])

    query = paginate_query(query, models.Schedule, ['id'],
                           limit=filter_args.get('limit'),
                           marker=marker_schedule)

    return query.all()


def _schedule_get_by_id(schedule_id, session=None):
    session = session or get_session()
    try:
        schedule = session.query(models.Schedule)\
                          .options(sa_orm.joinedload_all('schedule_metadata'))\
                          .filter_by(id=schedule_id)\
                          .one()
    except sa_orm.exc.NoResultFound:
        raise exception.NotFound()

    return schedule


@force_dict
def schedule_get_by_id(schedule_id):
    return _schedule_get_by_id(schedule_id)


@force_dict
def schedule_update(schedule_id, schedule_values):
    # make a copy so we can remove 'schedule_metadata'
    # without affecting the caller
    values = schedule_values.copy()
    session = get_session()
    schedule_ref = _schedule_get_by_id(schedule_id, session)

    if 'schedule_metadata' in values:
        metadata = values.pop('schedule_metadata')
        _schedule_metadata_update_in_place(schedule_ref, metadata)

    schedule_ref.update(values)
    schedule_ref.save(session=session)
    return _schedule_get_by_id(schedule_id)


def schedule_test_and_set_next_run(schedule_id, expected_next_run, next_run):
    session = get_session()
    if expected_next_run:
        query = session.query(models.Schedule).filter_by(id=schedule_id)\
                       .filter_by(next_run=expected_next_run)\
                       .update(dict(next_run=next_run))
    else:
        query = session.query(models.Schedule).filter_by(id=schedule_id)\
                       .update(dict(next_run=next_run))

    if not query:
        raise exception.NotFound()


def _schedule_metadata_update_in_place(schedule, metadata):
    new_meta = {}
    for item in metadata:
        new_meta[item['key']] = item['value']
    to_delete = []
    for meta in schedule.schedule_metadata:
        if not meta['key'] in new_meta:
            to_delete.append(meta)
        else:
            meta['value'] = new_meta[meta['key']]
            del new_meta[meta['key']]

    for key, value in new_meta.iteritems():
        meta_ref = models.ScheduleMetadata()
        meta_ref.key = key
        meta_ref.value = value
        schedule.schedule_metadata.append(meta_ref)

    for meta in to_delete:
        schedule['schedule_metadata'].remove(meta)


def schedule_delete(schedule_id):
    session = get_session()
    schedule_ref = _schedule_get_by_id(schedule_id, session)
    schedule_ref.delete(session=session)


def _set_schedule_metadata(schedule_ref, metadata):
    for metadatum in metadata:
        metadata_ref = models.ScheduleMetadata()
        metadata_ref.update(metadatum)
        schedule_ref.schedule_metadata.append(metadata_ref)

# Schedule Metadata methods


@force_dict
def schedule_meta_create(schedule_id, values):
    session = get_session()
    _schedule_get_by_id(schedule_id, session)
    meta_ref = models.ScheduleMetadata()
    values['schedule_id'] = schedule_id
    meta_ref.update(values)

    try:
        meta_ref.save(session=session)
    except sqlalchemy.exc.IntegrityError:
        raise exception.Duplicate()

    return _schedule_meta_get(schedule_id, values['key'])


@force_dict
def schedule_meta_get_all(schedule_id):
    session = get_session()
    _schedule_get_by_id(schedule_id, session)
    query = session.query(models.ScheduleMetadata)\
                   .filter_by(schedule_id=schedule_id)

    return query.all()


def _schedule_meta_get(schedule_id, key, session=None):
    session = session or get_session()
    try:
        _schedule_get_by_id(schedule_id, session)
    except exception.NotFound:
        msg = _('Schedule %s could not be found') % schedule_id
        raise exception.NotFound(message=msg)
    try:
        meta = session.query(models.ScheduleMetadata)\
                      .filter_by(schedule_id=schedule_id)\
                      .filter_by(key=key)\
                      .one()
    except sa_orm.exc.NoResultFound:
        raise exception.NotFound()

    return meta


def _schedule_meta_update(schedule_id, key, values):
    session = get_session()
    _schedule_get_by_id(schedule_id, session)
    meta_ref = _schedule_meta_get(schedule_id, key, session)
    meta_ref.update(values)
    meta_ref.save(session=session)
    return meta_ref


@force_dict
def schedule_metadata_update(schedule_id, values):
    session = get_session()
    schedule = _schedule_get_by_id(schedule_id, session)
    _schedule_metadata_update_in_place(schedule, values)

    schedule.save(session=session)

    return schedule_meta_get_all(schedule_id)


def schedule_meta_delete(schedule_id, key):
    session = get_session()
    _schedule_get_by_id(schedule_id, session)
    meta_ref = _schedule_meta_get(schedule_id, key, session)
    meta_ref.delete(session=session)


# Worker methods


@force_dict
def worker_get_all(params={}):
    session = get_session()
    query = session.query(models.Worker)

    marker_worker = None
    if params.get('marker') is not None:
        marker_worker = _worker_get_by_id(params['marker'])

    query = paginate_query(query, models.Worker, ['id'],
                           limit=params.get('limit'), marker=marker_worker)

    return query.all()


@force_dict
def worker_create(values):
    session = get_session()
    worker_ref = models.Worker()
    worker_ref.update(values)
    worker_ref.save(session=session)

    return _worker_get_by_id(worker_ref['id'])


def _worker_get_by_id(worker_id):
    session = get_session()
    query = session.query(models.Worker).filter_by(id=worker_id)

    try:
        worker = query.one()
    except sa_orm.exc.NoResultFound:
        raise exception.NotFound

    return worker


@force_dict
def worker_get_by_id(worker_id):
    return _worker_get_by_id(worker_id)


def worker_delete(worker_id):
    session = get_session()

    with session.begin():
        worker = _worker_get_by_id(worker_id)
        worker.delete(session=session)


# Job methods


@force_dict
def job_create(job_values):
    db_utils.validate_job_values(job_values)
    values = job_values.copy()
    session = get_session()
    job_ref = models.Job()

    if 'job_metadata' in values:
        metadata = values['job_metadata']
        _set_job_metadata(job_ref, metadata)
        del values['job_metadata']

    job_ref.update(values)
    job_ref.save(session=session)

    return _job_get_by_id(job_ref['id'])


def _filter_query_on_attributes(query, params, model, allowed_filters):
    for key in allowed_filters:
        if key in params:
            query = query.filter(
                getattr(model, key) == params[key])
            params.pop(key)

    return query


@force_dict
def job_get_all(params={}):
    session = get_session()
    query = session.query(models.Job)\
                   .options(sa_orm.subqueryload('job_metadata'))
    JOB_BASE_FILTERS = ['schedule_id',
                        'tenant',
                        'action',
                        'worker_id',
                        'status',
                        'timeout',
                        'hard_timeout']

    query = _filter_query_on_attributes(query,
                                        params,
                                        models.Job,
                                        JOB_BASE_FILTERS)

    marker_job = None
    if params.get('marker') is not None:
        marker_job = _job_get_by_id(params['marker'])

    query = paginate_query(query, models.Job, ['id'],
                           limit=params.get('limit'), marker=marker_job)

    return query.all()


def _job_get_by_id(job_id, session=None):
    session = session or get_session()
    try:
        job = session.query(models.Job)\
                     .options(sa_orm.subqueryload('job_metadata'))\
                     .filter_by(id=job_id)\
                     .one()
    except sa_orm.exc.NoResultFound:
        raise exception.NotFound()

    return job


@force_dict
def job_get_by_id(job_id):
    return _job_get_by_id(job_id)


def job_updated_at_get_by_id(job_id):
    return _job_get_by_id(job_id)['updated_at']


@force_dict
def job_get_and_assign_next_by_action(action, worker_id, new_timeout):
    """Get the next available job for the given action and assign it
    to the worker for worker_id."""
    now = timeutils.utcnow()
    session = get_session()

    job_ref = _job_get_next_by_action(session, now, action)

    if not job_ref:
        return None

    job_id = job_ref['id']
    try:
        job_values = {'worker_id': worker_id,
                      'timeout': new_timeout,
                      'retry_count': job_ref['retry_count'] + 1}

        job_ref.update(job_values)
        job_ref.save(session=session)
    except sa_orm.exc.NoResultFound:
        # In case the job was deleted during assignment return nothing
        LOG.warn(_('[JOB2WORKER] NoResultFound:'
                   ' Could not assign the job to worker_id: %(worker_id)s'
                   ' NoResultFound for job_id: %(job_id)s.')
                 % {'worker_id': job_values['worker_id'],
                    'job_id': job_id})
        return None
    except sa_orm.exc.StaleDataError:
        # In case the job was picked up by another transaction return nothing
        LOG.warn(_('[JOB2WORKER] StaleDataError:'
                   ' Could not assign the job to worker_id: %(worker_id)s'
                   ' Job already assigned to another worker,'
                   ' job_id: %(job_id)s.')
                 % {'worker_id': job_values['worker_id'],
                    'job_id': job_id})
        return None

    LOG.info(_('[JOB2WORKER] Assigned Job: %(job_id)s'
               ' To Worker: %(worker_id)s')
             % {'job_id': job_id, 'worker_id': job_values['worker_id']})

    return _job_get_by_id(job_id)


def _job_get_next_by_action(session, now, action):
    # Round off 'now' to minute precision to allow the SQL query cache to
    # do more work

    # Testing showed that lazyload is apparently fastest in our specific
    # case since we only fetch a single job here and there's only one
    # child table, hence only two simple queries vs. subqueryload which
    # issues as second more complex query or joinedload which issues
    # a single more complex join
    now_round_off = now.replace(second=0, microsecond=0)
    statuses = ['DONE', 'CANCELLED', 'HARD_TIMED_OUT', 'MAX_RETRIED']
    job_ref = session.query(models.Job)\
        .options(sa_orm.lazyload('job_metadata'))\
        .filter_by(action=action)\
        .filter(~models.Job.status.in_(statuses))\
        .filter(sa_sql.or_(models.Job.worker_id.is_(None),
                           models.Job.timeout <= now_round_off))\
        .order_by(models.Job.updated_at.asc())\
        .first()

    # Force loading of the job_metadata
    if job_ref is not None:
        m = job_ref['job_metadata']
        LOG.info(_('Job Metatdata forcefully loaded: %s' % m))

    return job_ref


def _jobs_cleanup_hard_timed_out():
    """Find all jobs with hard_timeout values which have passed
    and delete them, logging the timeout / failure as appropriate"""
    now = timeutils.utcnow()
    session = get_session()
    num_del = session.query(models.Job)\
        .filter(models.Job.hard_timeout <= now)\
        .delete()
    session.flush()
    return num_del


@force_dict
def job_update(job_id, job_values):
    # make a copy so we can remove 'job_metadata'
    # without affecting the caller
    values = job_values.copy()
    session = get_session()
    job_ref = _job_get_by_id(job_id, session)

    if 'job_metadata' in values:
        metadata = values.pop('job_metadata')
        _job_metadata_update_in_place(job_ref, metadata)

    job_ref.update(values)
    job_ref.save(session=session)
    return _job_get_by_id(job_id)


def _job_metadata_update_in_place(job, metadata):
    new_meta = {}
    for item in metadata:
        new_meta[item['key']] = item['value']
    to_delete = []
    for meta in job.job_metadata:
        if not meta['key'] in new_meta:
            to_delete.append(meta)
        else:
            meta['value'] = new_meta[meta['key']]
            del new_meta[meta['key']]

    for key, value in new_meta.iteritems():
        meta_ref = models.JobMetadata()
        meta_ref.key = key
        meta_ref.value = value
        job.job_metadata.append(meta_ref)

    for meta in to_delete:
        job['job_metadata'].remove(meta)


def job_delete(job_id):
    session = get_session()
    job_ref = _job_get_by_id(job_id)
    job_ref.delete(session=session)


def _set_job_metadata(job_ref, metadata):
    for metadatum in metadata:
        metadata_ref = models.JobMetadata()
        metadata_ref.update(metadatum)
        job_ref.job_metadata.append(metadata_ref)


@force_dict
def job_meta_create(job_id, values):
    values['job_id'] = job_id
    session = get_session()
    meta_ref = models.JobMetadata()
    meta_ref.update(values)

    try:
        meta_ref.save(session=session)
    except sqlalchemy.exc.IntegrityError:
        raise exception.Duplicate()

    return _job_meta_get_by_id(meta_ref['id'])


def _job_meta_get_by_id(meta_id):
    session = get_session()
    try:
        meta = session.query(models.JobMetadata)\
                      .filter_by(id=meta_id)\
                      .one()
    except sa_orm.exc.NoResultFound:
        raise exception.NotFound()

    return meta


def _job_meta_get_all_by_job_id(job_id):
    session = get_session()
    try:
        meta = session.query(models.JobMetadata)\
                      .filter_by(job_id=job_id)\
                      .all()
    except sa_orm.exc.NoResultFound:
        raise exception.NotFound()

    return meta


def _job_meta_get(job_id, key):
    session = get_session()
    try:
        meta = session.query(models.JobMetadata)\
                      .filter_by(job_id=job_id)\
                      .filter_by(key=key)\
                      .one()
    except sa_orm.exc.NoResultFound:
        raise exception.NotFound()

    return meta


@force_dict
def job_meta_get_all_by_job_id(job_id):
    return _job_meta_get_all_by_job_id(job_id)


@force_dict
def job_metadata_update(job_id, values):
    session = get_session()
    job = _job_get_by_id(job_id, session)
    _job_metadata_update_in_place(job, values)

    job.save(session=session)

    return job_meta_get_all_by_job_id(job_id)


# Job fault methods

def job_fault_latest_for_job_id(job_id):
    session = get_session()
    try:
        job_fault = session.query(models.JobFault)\
            .filter_by(job_id=job_id)\
            .order_by(models.JobFault.created_at.desc())\
            .first()
        return job_fault
    except sa_orm.exc.NoResultFound:
        return None


@force_dict
def job_fault_create(values):
    session = get_session()
    job_fault_ref = models.JobFault()
    job_fault_ref.update(values)

    job_fault_ref.save(session=session)

    return job_fault_ref
