# vim: tabstop=4 shiftwidth=4 softtabstop=4

#    Copyright 2014 Rackspace Hosting
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

from sqlalchemy import MetaData, Table, Index

INDEX_STATUS_NAME = 'status_idx'
INDEX_TIMEOUT_NAME = 'timeout_idx'


def upgrade(migrate_engine):
    meta = MetaData()
    meta.bind = migrate_engine

    jobs = Table('jobs', meta, autoload=True)

    index = Index(INDEX_STATUS_NAME, jobs.c.status)
    index.create(migrate_engine)

    index = Index(INDEX_TIMEOUT_NAME, jobs.c.timeout)
    index.create(migrate_engine)


def downgrade(migrate_engine):
    meta = MetaData()
    meta.bind = migrate_engine

    jobs = Table('jobs', meta, autoload=True)

    index = Index(INDEX_STATUS_NAME, jobs.c.status)
    index.drop(migrate_engine)

    index = Index(INDEX_TIMEOUT_NAME, jobs.c.timeout)
    index.drop(migrate_engine)
