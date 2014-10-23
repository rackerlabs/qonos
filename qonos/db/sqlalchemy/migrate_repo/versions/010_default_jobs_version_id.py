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

from sqlalchemy.schema import Column
from sqlalchemy.schema import MetaData
from sqlalchemy.schema import Table

from qonos.db.sqlalchemy.migrate_repo.schema import DateTime
from qonos.db.sqlalchemy.migrate_repo.schema import Integer
from qonos.db.sqlalchemy.migrate_repo.schema import String


def get_jobs_table(meta):
    jobs = Table('jobs',
                 meta,
                 Column('id', String(36), primary_key=True, nullable=False),
                 Column('schedule_id', String(36)),
                 Column('tenant', String(255), nullable=False),
                 Column('worker_id', String(36), nullable=True),
                 Column('status', String(255), nullable=True),
                 Column('action', String(255), nullable=False),
                 Column('retry_count', Integer(), nullable=False, default=0),
                 Column('timeout', DateTime(), nullable=False),
                 Column('hard_timeout', DateTime(), nullable=False),
                 Column('version_id', String(36)),
                 Column('created_at', DateTime(), nullable=False),
                 Column('updated_at', DateTime(), nullable=False),
                 mysql_engine='InnoDB',
                 mysql_charset='utf8',
                 extend_existing=True)

    return jobs


def upgrade(migrate_engine):
    meta = MetaData()
    meta.bind = migrate_engine

    jobs_table = get_jobs_table(meta)

    conn = migrate_engine.connect()
    conn.execute(jobs_table.update(jobs_table.c.version_id.is_(None),
                                   {jobs_table.c.version_id: jobs_table.c.id}))


def downgrade(migrate_engine):
    meta = MetaData()
    meta.bind = migrate_engine

    jobs_table = get_jobs_table(meta)

    conn = migrate_engine.connect()
    conn.execute(jobs_table.update(jobs_table.c.version_id == jobs_table.c.id,
                                   {jobs_table.c.version_id: None}))
