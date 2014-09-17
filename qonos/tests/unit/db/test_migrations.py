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
Tests for database migrations. This test case reads the configuration
file /tests/unit/test_migrations.conf for database connection settings
to use in the tests. For each connection found in the config file,
the test case runs a series of test cases to ensure that migrations work
properly both upgrading and downgrading, and that no data loss occurs
if possible.
"""

from __future__ import print_function

import commands
import ConfigParser
import datetime
import os
import urlparse

from migrate.versioning.repository import Repository
from oslo.config import cfg
import sqlalchemy

import qonos.db.migration as migration
import qonos.db.sqlalchemy.migrate_repo
from qonos.db.sqlalchemy.migration import versioning_api as migration_api
from qonos.openstack.common import log as logging
from qonos.openstack.common import uuidutils
from qonos.tests import utils


CONF = cfg.CONF

LOG = logging.getLogger(__name__)


def _get_connect_string(backend,
                        user="qonos_citest",
                        passwd="qonos_citest",
                        database="qonos_citest"):
    """
    Try to get a connection with a very specific set of values, if we get
    these then we'll run the tests, otherwise they are skipped
    """
    if backend == "mysql":
        backend = "mysql+mysqldb"
    elif backend == "postgres":
        backend = "postgresql+psycopg2"

    return ("%(backend)s://%(user)s:%(passwd)s@localhost/%(database)s"
            % locals())


def _is_backend_avail(backend,
                      user="qonos_citest",
                      passwd="qonos_citest",
                      database="qonos_citest"):
    try:
        if backend == "mysql":
            connect_uri = _get_connect_string("mysql", user=user,
                                              passwd=passwd, database=database)
        elif backend == "postgres":
            connect_uri = _get_connect_string("postgres", user=user,
                                              passwd=passwd, database=database)
        engine = sqlalchemy.create_engine(connect_uri)
        connection = engine.connect()
    except Exception:
        # intentionally catch all to handle exceptions even if we don't
        # have any backend code loaded.
        return False
    else:
        connection.close()
        engine.dispose()
        return True


def _have_mysql():
    present = os.environ.get('QONOS_TEST_MYSQL_PRESENT')
    if present is None:
        return _is_backend_avail('mysql')
    return present.lower() in ('', 'true')


def get_table(engine, name):
    """Returns an sqlalchemy table dynamically from db.

    Needed because the models don't work for us in migrations
    as models will be far out of sync with the current data.
    """
    metadata = sqlalchemy.schema.MetaData()
    metadata.bind = engine
    return sqlalchemy.Table(name, metadata, autoload=True)


class TestMigrations(utils.BaseTestCase):
    """Test sqlalchemy-migrate migrations."""

    DEFAULT_CONFIG_FILE = os.path.join(os.path.dirname(__file__),
                                       'test_migrations.conf')
    # Test machines can set the QONOS_TEST_MIGRATIONS_CONF variable
    # to override the location of the config file for migration testing
    CONFIG_FILE_PATH = os.environ.get('QONOS_TEST_MIGRATIONS_CONF',
                                      DEFAULT_CONFIG_FILE)
    MIGRATE_FILE = qonos.db.sqlalchemy.migrate_repo.__file__
    REPOSITORY = Repository(os.path.abspath(os.path.dirname(MIGRATE_FILE)))

    def setUp(self):
        super(TestMigrations, self).setUp()

        self.snake_walk = False
        self.test_databases = {}

        # Load test databases from the config file. Only do this
        # once. No need to re-run this on each test...
        LOG.debug('config_path is %s' % TestMigrations.CONFIG_FILE_PATH)
        if os.path.exists(TestMigrations.CONFIG_FILE_PATH):
            cp = ConfigParser.RawConfigParser()
            try:
                cp.read(TestMigrations.CONFIG_FILE_PATH)
                defaults = cp.defaults()
                for key, value in defaults.items():
                    self.test_databases[key] = value
                self.snake_walk = cp.getboolean('walk_style', 'snake_walk')
            except ConfigParser.ParsingError as e:
                self.fail("Failed to read test_migrations.conf config "
                          "file. Got error: %s" % e)
        else:
            self.fail("Failed to find test_migrations.conf config "
                      "file.")

        self.engines = {}
        for key, value in self.test_databases.items():
            self.engines[key] = sqlalchemy.create_engine(value)

        # We start each test case with a completely blank slate.
        self._reset_databases()

    def tearDown(self):
        # We destroy the test data store between each test case,
        # and recreate it, which ensures that we have no side-effects
        # from the tests
        self._reset_databases()
        super(TestMigrations, self).tearDown()

    def _reset_databases(self):
        def execute_cmd(cmd=None):
            status, output = commands.getstatusoutput(cmd)
            LOG.debug(output)
            self.assertEqual(0, status)
        for key, engine in self.engines.items():
            conn_string = self.test_databases[key]
            conn_pieces = urlparse.urlparse(conn_string)
            engine.dispose()
            if conn_string.startswith('sqlite'):
                # We can just delete the SQLite database, which is
                # the easiest and cleanest solution
                db_path = conn_pieces.path.strip('/')
                if os.path.exists(db_path):
                    os.unlink(db_path)
                # No need to recreate the SQLite DB. SQLite will
                # create it for us if it's not there...
            elif conn_string.startswith('mysql'):
                # We can execute the MySQL client to destroy and re-create
                # the MYSQL database, which is easier and less error-prone
                # than using SQLAlchemy to do this via MetaData...trust me.
                database = conn_pieces.path.strip('/')
                loc_pieces = conn_pieces.netloc.split('@')
                host = loc_pieces[1]
                auth_pieces = loc_pieces[0].split(':')
                user = auth_pieces[0]
                password = ""
                if len(auth_pieces) > 1:
                    if auth_pieces[1].strip():
                        password = "-p\"%s\"" % auth_pieces[1]
                sql = ("drop database if exists %(database)s; "
                       "create database %(database)s;") % locals()
                cmd = ("mysql -u \"%(user)s\" %(password)s -h %(host)s "
                       "-e \"%(sql)s\"") % locals()
                execute_cmd(cmd)
            elif conn_string.startswith('postgresql'):
                database = conn_pieces.path.strip('/')
                loc_pieces = conn_pieces.netloc.split('@')
                host = loc_pieces[1]

                auth_pieces = loc_pieces[0].split(':')
                user = auth_pieces[0]
                password = ""
                if len(auth_pieces) > 1:
                    password = auth_pieces[1].strip()
                # note(boris-42): This file is used for authentication
                # without password prompt.
                createpgpass = ("echo '*:*:*:%(user)s:%(password)s' > "
                                "~/.pgpass && chmod 0600 ~/.pgpass" % locals())
                execute_cmd(createpgpass)
                # note(boris-42): We must create and drop database, we can't
                # drop database which we have connected to, so for such
                # operations there is a special database template1.
                sqlcmd = ("psql -w -U %(user)s -h %(host)s -c"
                          " '%(sql)s' -d template1")
                sql = ("drop database if exists %(database)s;") % locals()
                droptable = sqlcmd % locals()
                execute_cmd(droptable)
                sql = ("create database %(database)s;") % locals()
                createtable = sqlcmd % locals()
                execute_cmd(createtable)

    def test_walk_versions(self):
        """
        Walks all version scripts for each tested database, ensuring
        that there are no errors in the version scripts for each engine
        """
        for key, engine in self.engines.items():
            self._walk_versions(engine, self.snake_walk)

    def test_mysql_connect_fail(self):
        """
        Test that we can trigger a mysql connection failure and we fail
        gracefully to ensure we don't break people without mysql
        """
        if _is_backend_avail('mysql', user="qonos_cifail"):
            self.fail("Shouldn't have connected")

    def test_mysql_opportunistically(self):
        # Test that table creation on mysql only builds InnoDB tables
        if not _is_backend_avail('mysql'):
            self.skipTest("mysql not available")
        # add this to the global lists to make reset work with it, it's removed
        # automatically in tearDown so no need to clean it up here.
        connect_string = _get_connect_string("mysql")
        engine = sqlalchemy.create_engine(connect_string)
        self.engines["mysqlcitest"] = engine
        self.test_databases["mysqlcitest"] = connect_string

        # build a fully populated mysql database with all the tables
        self._reset_databases()
        self._walk_versions(engine, False, False)

        connection = engine.connect()
        # sanity check
        total = connection.execute("SELECT count(*) "
                                   "from information_schema.TABLES "
                                   "where TABLE_SCHEMA='qonos_citest'")
        self.assertTrue(total.scalar() > 0, "No tables found. Wrong schema?")

        noninnodb = connection.execute("SELECT count(*) "
                                       "from information_schema.TABLES "
                                       "where TABLE_SCHEMA='qonos_citest' "
                                       "and ENGINE!='InnoDB' "
                                       "and TABLE_NAME!='migrate_version'")
        count = noninnodb.scalar()
        self.assertEqual(count, 0, "%d non InnoDB tables created" % count)
        connection.close()

    def test_postgresql_connect_fail(self):
        """
        Test that we can trigger a postgres connection failure and we fail
        gracefully to ensure we don't break people without postgres
        """
        if _is_backend_avail('postgresql', user="qonos_cifail"):
            self.fail("Shouldn't have connected")

    def test_postgresql_opportunistically(self):
        # Test postgresql database migration walk
        if not _is_backend_avail('postgres'):
            self.skipTest("postgresql not available")
        # add this to the global lists to make reset work with it, it's removed
        # automatically in tearDown so no need to clean it up here.
        connect_string = _get_connect_string("postgres")
        engine = sqlalchemy.create_engine(connect_string)
        self.engines["postgresqlcitest"] = engine
        self.test_databases["postgresqlcitest"] = connect_string

        # build a fully populated postgresql database with all the tables
        self._reset_databases()
        self._walk_versions(engine, False, False)

    def _walk_versions(self, engine=None, snake_walk=False, downgrade=True,
                       initial_version=None):
        # Determine latest version script from the repo, then
        # upgrade from 1 through to the latest, with no data
        # in the databases. This just checks that the schema itself
        # upgrades successfully.

        def db_version():
            return migration_api.db_version(engine, TestMigrations.REPOSITORY)

        # Place the database under version control
        init_version = migration.INIT_VERSION
        if initial_version is not None:
            init_version = initial_version
        migration_api.version_control(engine, TestMigrations.REPOSITORY,
                                      init_version)
        self.assertEqual(init_version, db_version())

        migration_api.upgrade(engine, TestMigrations.REPOSITORY,
                              init_version + 1)
        self.assertEqual(init_version + 1, db_version())

        LOG.debug('latest version is %s' % TestMigrations.REPOSITORY.latest)

        for version in xrange(init_version + 2,
                              TestMigrations.REPOSITORY.latest + 1):
            # upgrade -> downgrade -> upgrade
            self._migrate_up(engine, version, with_data=True)
            if snake_walk:
                self._migrate_down(engine, version - 1, with_data=True)
                self._migrate_up(engine, version)

        if downgrade:
            # Now walk it back down to 0 from the latest, testing
            # the downgrade paths.
            for version in reversed(
                xrange(init_version + 2,
                       TestMigrations.REPOSITORY.latest + 1)):
                # downgrade -> upgrade -> downgrade
                self._migrate_down(engine, version - 1)
                if snake_walk:
                    self._migrate_up(engine, version)
                    self._migrate_down(engine, version - 1)

            # Ensure we made it all the way back to the first migration
            self.assertEqual(init_version + 1, db_version())

    def _migrate_down(self, engine, version, with_data=False):
        migration_api.downgrade(engine,
                                TestMigrations.REPOSITORY,
                                version)
        self.assertEqual(version,
                         migration_api.db_version(engine,
                                                  TestMigrations.REPOSITORY))

        # NOTE(sirp): `version` is what we're downgrading to (i.e. the 'target'
        # version). So if we have any downgrade checks, they need to be run for
        # the previous (higher numbered) migration.
        if with_data:
            post_downgrade = getattr(self, "_post_downgrade_%03d" %
                                           (version + 1), None)
            if post_downgrade:
                post_downgrade(engine)

    def _migrate_up(self, engine, version, with_data=False):
        """migrate up to a new version of the db.

        We allow for data insertion and post checks at every
        migration version with special _pre_upgrade_### and
        _check_### functions in the main test.
        """
        if with_data:
            data = None
            pre_upgrade = getattr(self, "_pre_upgrade_%3.3d" % version, None)
            if pre_upgrade:
                data = pre_upgrade(engine)

        migration_api.upgrade(engine,
                              TestMigrations.REPOSITORY,
                              version)
        self.assertEqual(version,
                         migration_api.db_version(engine,
                                                  TestMigrations.REPOSITORY))

        if with_data:
            check = getattr(self, "_check_%3.3d" % version, None)
            if check:
                check(engine, data)

    def _create_unversioned_001_db(self, engine):
        # Create the initial version of the schedules table
        meta = sqlalchemy.schema.MetaData()
        meta.bind = engine

        schedules_001 = sqlalchemy.Table(
            'schedules',
            meta,
            sqlalchemy.Column('id', sqlalchemy.String(36), primary_key=True),
            sqlalchemy.Column('tenant', sqlalchemy.String(255),
                              nullable=False),
            sqlalchemy.Column('action', sqlalchemy.String(255),
                              nullable=False),
            sqlalchemy.Column('minute', sqlalchemy.Integer),
            sqlalchemy.Column('hour', sqlalchemy.Integer),
            sqlalchemy.Column('day_of_month', sqlalchemy.Integer),
            sqlalchemy.Column('month', sqlalchemy.Integer),
            sqlalchemy.Column('day_of_week', sqlalchemy.Integer),
            sqlalchemy.Column('last_scheduled', sqlalchemy.DateTime),
            sqlalchemy.Column('next_run', sqlalchemy.DateTime),
            sqlalchemy.Column('created_at', sqlalchemy.DateTime,
                              nullable=False),
            sqlalchemy.Column('updated_at', sqlalchemy.DateTime)
        )

        schedules_001.create()

    def test_version_control_existing_db(self):
        """
        Creates a DB without version control information, places it
        under version control and checks that it can be upgraded
        without errors.
        """
        for key, engine in self.engines.items():
            self._create_unversioned_001_db(engine)
            self._walk_versions(engine, self.snake_walk, initial_version=1)

    def _assert_script_001(self, meta):
        schedules_table = sqlalchemy.Table('schedules', meta, autoload=True)
        expected_col_names = [
            u'id',
            u'tenant',
            u'action',
            u'minute',
            u'hour',
            u'day_of_month',
            u'month',
            u'day_of_week',
            u'last_scheduled',
            u'next_run',
            u'created_at',
            u'updated_at',
        ]
        col_names = [col.name for col in schedules_table.columns]
        self.assertEqual(expected_col_names, col_names)

        #try insert and fetch a record
        # Setting microsecond to 0 because using MySQL it only goes to seconds
        now = datetime.datetime.now().replace(microsecond=0)
        ins_schedule = {
            'id': 'WORKER-1',
            'tenant': 'OWNER-1',
            'action': 'snapshot',
            'minute': 30,
            'hour': 1,
            'day_of_month': 1,
            'month': 12,
            'day_of_week': 1,
            'last_scheduled': now,
            'next_run': now,
            'created_at': now,
            'updated_at': now
        }
        schedules_table.insert().values(ins_schedule).execute()
        ret_schedules = schedules_table.select().execute().fetchall()

        self.assertEqual(1, len(ret_schedules))
        self.assertEqual(ins_schedule['id'], ret_schedules[0]['id'])
        self.assertEqual(ins_schedule['tenant'], ret_schedules[0]['tenant'])
        self.assertEqual(ins_schedule['action'], ret_schedules[0]['action'])
        self.assertEqual(ins_schedule['minute'], ret_schedules[0]['minute'])
        self.assertEqual(ins_schedule['hour'], ret_schedules[0]['hour'])
        self.assertEqual(ins_schedule['day_of_month'],
                         ret_schedules[0]['day_of_month'])
        self.assertEqual(ins_schedule['month'], ret_schedules[0]['month'])
        self.assertEqual(ins_schedule['day_of_week'],
                         ret_schedules[0]['day_of_week'])
        self.assertEqual(ins_schedule['last_scheduled'],
                         ret_schedules[0]['last_scheduled'])
        self.assertEqual(ins_schedule['next_run'],
                         ret_schedules[0]['next_run'])
        datetime_without_msec = "%Y-%m-%d %H:%M:%S"
        self.assertEqual(
            ins_schedule['created_at'].strftime(datetime_without_msec),
            ret_schedules[0]['created_at'].strftime(datetime_without_msec)
        )
        self.assertEqual(
            ins_schedule['updated_at'].strftime(datetime_without_msec),
            ret_schedules[0]['updated_at'].strftime(datetime_without_msec)
        )

    def _assert_script_002(self, meta):
        schedule_metadata_table = sqlalchemy.Table('schedule_metadata',
                                                   meta,
                                                   autoload=True)
        expected_col_names = [
            u'id',
            u'schedule_id',
            u'key',
            u'value',
            u'created_at',
            u'updated_at',
        ]
        col_names = [col.name for col in schedule_metadata_table.columns]
        self.assertEqual(expected_col_names, col_names)

        #try insert and fetch a record
        now = datetime.datetime.now()
        ins_schedule_metadata = {
            'id': 'WORKER-1',
            'schedule_id': 'SCHD-1',
            'key': 'some_key',
            'value': 'some_value',
            'created_at': now,
            'updated_at': now
        }
        schedule_metadata_table.insert().\
            values(ins_schedule_metadata).execute()
        ret_schedule_metadata = schedule_metadata_table.select()\
            .execute().fetchall()

        self.assertEqual(1, len(ret_schedule_metadata))
        self.assertEqual(ins_schedule_metadata['id'],
                         ret_schedule_metadata[0]['id'])
        self.assertEqual(ins_schedule_metadata['schedule_id'],
                         ret_schedule_metadata[0]['schedule_id'])
        self.assertEqual(ins_schedule_metadata['key'],
                         ret_schedule_metadata[0]['key'])
        self.assertEqual(ins_schedule_metadata['value'],
                         ret_schedule_metadata[0]['value'])
        datetime_without_msec = "%Y-%m-%d %H:%M:%S"
        self.assertEqual(
            ins_schedule_metadata['created_at']
            .strftime(datetime_without_msec),
            ret_schedule_metadata[0]['created_at']
            .strftime(datetime_without_msec)
        )
        self.assertEqual(
            ins_schedule_metadata['updated_at']
            .strftime(datetime_without_msec),
            ret_schedule_metadata[0]['updated_at']
            .strftime(datetime_without_msec)
        )

    def _check_003(self, engine, data):
        meta = sqlalchemy.MetaData()
        meta.bind = engine

        # Note (venkatesh) temporarily testing scripts 001 & 002 here.
        # need to find a better way to test them separately.
        # _check_001
        self._assert_script_001(meta)

        # _check_002
        self._assert_script_002(meta)

        # _check_003
        workers_table = sqlalchemy.Table('workers', meta, autoload=True)

        expected_col_names = [
            u'id',
            u'host',
            u'process_id',
            u'created_at',
            u'updated_at',
        ]

        col_names = [col.name for col in workers_table.columns]
        self.assertEqual(expected_col_names, col_names)

        #try insert and fetch a record
        now = datetime.datetime.now()
        ins_worker = {
            'id': 'WORKER-1',
            'host': 'localhost',
            'process_id': 12345,
            'created_at': now,
            'updated_at': now
        }
        workers_table.insert().values(ins_worker).execute()
        ret_workers = workers_table.select().execute().fetchall()

        self.assertEqual(1, len(ret_workers))
        self.assertEqual(ins_worker['id'], ret_workers[0]['id'])
        self.assertEqual(ins_worker['host'], ret_workers[0]['host'])
        self.assertEqual(ins_worker['process_id'],
                         ret_workers[0]['process_id'])
        datetime_without_msec = "%Y-%m-%d %H:%M:%S"
        self.assertEqual(
            ins_worker['created_at'].strftime(datetime_without_msec),
            ret_workers[0]['created_at'].strftime(datetime_without_msec)
        )
        self.assertEqual(
            ins_worker['updated_at'].strftime(datetime_without_msec),
            ret_workers[0]['updated_at'].strftime(datetime_without_msec)
        )

    def _post_downgrade_003(self, engine):
        self.assertRaises(sqlalchemy.exc.NoSuchTableError,
                          get_table, engine, 'workers')

    def _check_004(self, engine, data):
        meta = sqlalchemy.MetaData()
        meta.bind = engine

        jobs_table = sqlalchemy.Table('jobs', meta, autoload=True)

        expected_col_names = [
            u'id',
            u'schedule_id',
            u'tenant',
            u'worker_id',
            u'status',
            u'action',
            u'retry_count',
            u'timeout',
            u'hard_timeout',
            u'created_at',
            u'updated_at',
        ]

        col_names = [col.name for col in jobs_table.columns]
        self.assertEqual(expected_col_names, col_names)

        #try insert and fetch a record
        now = datetime.datetime.now()

        ins_job = {
            'id': 'JOB-1',
            'schedule_id': 'SCHD-1',
            'tenant': 'OWNER-1',
            'worker_id': 'WORKER-1',
            'status': 'success',
            'action': 'snapshot',
            'retry_count': 3,
            'timeout': now,
            'hard_timeout': now,
            'created_at': now,
            'updated_at': now
        }
        jobs_table.insert().values(ins_job).execute()
        ret_jobs = jobs_table.select().execute().fetchall()

        self.assertEqual(1, len(ret_jobs))
        self.assertEqual(ins_job['id'], ret_jobs[0]['id'])
        self.assertEqual(ins_job['schedule_id'], ret_jobs[0]['schedule_id'])
        self.assertEqual(ins_job['tenant'], ret_jobs[0]['tenant'])
        self.assertEqual(ins_job['worker_id'], ret_jobs[0]['worker_id'])
        self.assertEqual(ins_job['status'], ret_jobs[0]['status'])
        self.assertEqual(ins_job['action'], ret_jobs[0]['action'])
        self.assertEqual(ins_job['retry_count'], ret_jobs[0]['retry_count'])
        datetime_without_msec = "%Y-%m-%d %H:%M:%S"
        self.assertEqual(
            ins_job['timeout'].strftime(datetime_without_msec),
            ret_jobs[0]['timeout'].strftime(datetime_without_msec)
        )
        self.assertEqual(
            ins_job['hard_timeout'].strftime(datetime_without_msec),
            ret_jobs[0]['hard_timeout'].strftime(datetime_without_msec)
        )
        self.assertEqual(
            ins_job['created_at'].strftime(datetime_without_msec),
            ret_jobs[0]['created_at'].strftime(datetime_without_msec)
        )
        self.assertEqual(
            ins_job['updated_at'].strftime(datetime_without_msec),
            ret_jobs[0]['updated_at'].strftime(datetime_without_msec)
        )

    def _post_downgrade_004(self, engine):
        self.assertRaises(sqlalchemy.exc.NoSuchTableError,
                          get_table, engine, 'jobs')

    def _check_005(self, engine, data):
        meta = sqlalchemy.MetaData()
        meta.bind = engine

        job_metadata_table = sqlalchemy.Table('job_metadata',
                                              meta,
                                              autoload=True)
        expected_col_names = [
            u'id',
            u'job_id',
            u'key',
            u'value',
            u'created_at',
            u'updated_at',
        ]

        col_names = [col.name for col in job_metadata_table.columns]
        self.assertEqual(expected_col_names, col_names)

        #try insert and fetch a record
        now = datetime.datetime.now()

        ins_job_metadata = {
            'id': 'JOB-META-1',
            'job_id': 'JOB-1',
            'key': 'some_key',
            'value': 'some_value',
            'created_at': now,
            'updated_at': now
        }
        job_metadata_table.insert().values(ins_job_metadata).execute()
        ret_job_metadata = job_metadata_table.select().execute().fetchall()

        self.assertEqual(1, len(ret_job_metadata))
        self.assertEqual(ins_job_metadata['id'], ret_job_metadata[0]['id'])
        self.assertEqual(ins_job_metadata['key'], ret_job_metadata[0]['key'])
        self.assertEqual(ins_job_metadata['value'],
                         ret_job_metadata[0]['value'])
        datetime_without_msec = "%Y-%m-%d %H:%M:%S"
        self.assertEqual(
            ins_job_metadata['created_at'].strftime(datetime_without_msec),
            ret_job_metadata[0]['created_at'].strftime(datetime_without_msec)
        )
        self.assertEqual(
            ins_job_metadata['updated_at'].strftime(datetime_without_msec),
            ret_job_metadata[0]['updated_at'].strftime(datetime_without_msec)
        )

    def _post_downgrade_005(self, engine):
        self.assertRaises(sqlalchemy.exc.NoSuchTableError,
                          get_table, engine, 'job_metadata')

    def _check_006(self, engine, data):
        meta = sqlalchemy.MetaData()
        meta.bind = engine

        job_faults_table = sqlalchemy.Table('job_faults', meta, autoload=True)

        expected_col_names = [
            u'id',
            u'job_id',
            u'schedule_id',
            u'tenant',
            u'worker_id',
            u'action',
            u'message',
            u'job_metadata',
            u'created_at',
            u'updated_at',
        ]

        col_names = [col.name for col in job_faults_table.columns]
        self.assertEqual(expected_col_names, col_names)

        #try insert and fetch a record
        now = datetime.datetime.now()

        ins_job_fault = {
            'id': 'JOB-META-1',
            'job_id': 'JOB-1',
            'schedule_id': 'SCHD-1',
            'tenant': 'OWNER-1',
            'worker_id': 'WORKER-1',
            'action': '{snapshot:true}',
            'message': 'Error Occurred',
            'job_metadata': '{key1:value1, key2:value2}',
            'created_at': now,
            'updated_at': now
        }
        job_faults_table.insert().values(ins_job_fault).execute()
        ret_job_faults = job_faults_table.select().execute().fetchall()

        self.assertEqual(1, len(ret_job_faults))
        self.assertEqual(ins_job_fault['id'], ret_job_faults[0]['id'])
        self.assertEqual(ins_job_fault['job_id'], ret_job_faults[0]['job_id'])
        self.assertEqual(ins_job_fault['schedule_id'],
                         ret_job_faults[0]['schedule_id'])
        self.assertEqual(ins_job_fault['tenant'], ret_job_faults[0]['tenant'])
        self.assertEqual(ins_job_fault['worker_id'],
                         ret_job_faults[0]['worker_id'])
        self.assertEqual(ins_job_fault['action'], ret_job_faults[0]['action'])
        self.assertEqual(ins_job_fault['message'],
                         ret_job_faults[0]['message'])
        self.assertEqual(ins_job_fault['job_metadata'],
                         ret_job_faults[0]['job_metadata'])
        datetime_without_msec = "%Y-%m-%d %H:%M:%S"
        self.assertEqual(
            ins_job_fault['created_at'].strftime(datetime_without_msec),
            ret_job_faults[0]['created_at'].strftime(datetime_without_msec)
        )
        self.assertEqual(
            ins_job_fault['updated_at'].strftime(datetime_without_msec),
            ret_job_faults[0]['updated_at'].strftime(datetime_without_msec)
        )

    def _post_downgrade_006(self, engine):
        self.assertRaises(sqlalchemy.exc.NoSuchTableError,
                          get_table, engine, 'job_faults')

    def _check_007(self, engine, data):
        jobs = get_table(engine, 'jobs')
        self.assertTrue('version_id' in jobs.c.keys())

    def _post_downgrade_007(self, engine):
        jobs = get_table(engine, 'jobs')
        self.assertFalse('version_id' in jobs.c.keys())

    def _check_008(self, engine, data):
        table = "schedules"
        index = "next_run_idx"
        columns = ["next_run"]

        meta = sqlalchemy.MetaData()
        meta.bind = engine

        new_table = sqlalchemy.Table(table, meta, autoload=True)

        index_data = [(idx.name, idx.columns.keys())
                      for idx in new_table.indexes]

        self.assertIn((index, columns), index_data)

    def _post_downgrade_008(self, engine):
        table = "schedules"
        index = "next_run_idx"
        columns = ["next_run"]

        meta = sqlalchemy.MetaData()
        meta.bind = engine

        new_table = sqlalchemy.Table(table, meta, autoload=True)

        index_data = [(idx.name, idx.columns.keys())
                      for idx in new_table.indexes]

        self.assertNotIn((index, columns), index_data)

    def _check_009(self, engine, data):
        table = "jobs"
        index = "hard_timeout_idx"
        columns = ["hard_timeout"]
        meta = sqlalchemy.MetaData()
        meta.bind = engine

        new_table = sqlalchemy.Table(table, meta, autoload=True)

        index_data = [(idx.name, idx.columns.keys())
                      for idx in new_table.indexes]

        self.assertIn((index, columns), index_data)

    def _post_downgrade_009(self, engine):
        table = "jobs"
        index = "hard_timeout_idx"
        columns = ["hard_timeout"]
        meta = sqlalchemy.MetaData()
        meta.bind = engine

        new_table = sqlalchemy.Table(table, meta, autoload=True)

        index_data = [(idx.name, idx.columns.keys())
                      for idx in new_table.indexes]

        self.assertNotIn((index, columns), index_data)

    def _pre_upgrade_010(self, engine):
        initial_values = [
            ('JOB-1', uuidutils.generate_uuid()),
            ('JOB-2', uuidutils.generate_uuid()),
            ('JOB-3', None),
            ('JOB-4', None),
            ('JOB-5', None),
        ]

        jobs_table = get_table(engine, 'jobs')
        for job_id, version_id in initial_values:
            now = datetime.datetime.now()
            new_job = {
                'id': job_id,
                'schedule_id': 'SCHD-1',
                'tenant': 'OWNER-1',
                'worker_id': 'WORKER-1',
                'status': 'success',
                'action': 'snapshot',
                'retry_count': 3,
                'timeout': now,
                'hard_timeout': now,
                'version_id': version_id,
                'created_at': now,
                'updated_at': now
            }

            jobs_table.insert().values(new_job).execute()

        return initial_values

    def _check_010(self, engine, data):
        values = dict((jid, vid) for jid, vid in data)

        jobs = get_table(engine, 'jobs')
        for row in jobs.select().execute():
            if row['id'] in values:
                version_id = values.pop(row['id']) or row['id']
                self.assertEqual(row['version_id'], version_id)

        self.assertEqual(len(values), 0)

    def _post_downgrade_010(self, engine):
        jobs = get_table(engine, 'jobs')

        # for jobs with no version_id
        expected_job_ids = set(['JOB-3', 'JOB-4', 'JOB-5'])
        results = jobs.select().where(
            jobs.c.version_id == None).execute().fetchall()
        actual_job_ids = set(row['id'] for row in results)
        self.assertEqual(actual_job_ids, expected_job_ids)

        # for jobs with version_id
        expected_job_ids = set(['JOB-1', 'JOB-2'])
        results = jobs.select().where(
            jobs.c.version_id != None).execute().fetchall()
        actual_job_ids = set(row['id'] for row in results)
        self.assertEqual(actual_job_ids, expected_job_ids)

    def _check_011(self, engine, data):
        table = "job_metadata"
        meta = sqlalchemy.MetaData()
        meta.bind = engine

        new_table = sqlalchemy.Table(table, meta, autoload=True)

        self.assertTrue(len(new_table.foreign_keys), 1)

    def _check_012(self, engine, data):
        table = "schedule_metadata"
        meta = sqlalchemy.MetaData()
        meta.bind = engine

        new_table = sqlalchemy.Table(table, meta, autoload=True)

        self.assertTrue(len(new_table.foreign_keys), 1)

    def _check_013(self, engine, data):
        jobs = get_table(engine, 'jobs')

        # So, this value comes back in a kid of odd format
        self.assertEqual(u"'QUEUED'", jobs.c.status.server_default.arg.text)
        self.assertFalse(jobs.c.status.nullable)

    def _post_downgrade_013(self, engine):
        jobs = get_table(engine, 'jobs')

        self.assertEqual(None, jobs.c.status.server_default)
        self.assertTrue(jobs.c.status.nullable)

    def _check_014(self, engine, data):
        table = "jobs"
        index_status = "status_idx"
        columns_status = ["status"]
        index_timeout = "timeout_idx"
        columns_timeout = ["timeout"]
        meta = sqlalchemy.MetaData()
        meta.bind = engine

        new_table = sqlalchemy.Table(table, meta, autoload=True)

        index_data = [(idx.name, idx.columns.keys())
                      for idx in new_table.indexes]

        self.assertIn((index_status, columns_status), index_data)
        self.assertIn((index_timeout, columns_timeout), index_data)

    def _post_downgrade_014(self, engine):
        table = "jobs"
        index_status = "status_idx"
        columns_status = ["status"]
        index_timeout = "timeout_idx"
        columns_timeout = ["timeout"]
        meta = sqlalchemy.MetaData()
        meta.bind = engine

        new_table = sqlalchemy.Table(table, meta, autoload=True)

        index_data = [(idx.name, idx.columns.keys())
                      for idx in new_table.indexes]

        self.assertNotIn((index_status, columns_status), index_data)
        self.assertNotIn((index_timeout, columns_timeout), index_data)
