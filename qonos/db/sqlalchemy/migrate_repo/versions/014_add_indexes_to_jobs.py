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

from qonos.openstack.common._i18n import _
import qonos.openstack.common.log as logging

LOG = logging.getLogger(__name__)

INDEX_STATUS_NAME = 'status_idx'
INDEX_TIMEOUT_NAME = 'timeout_idx'


def _has_index(indexes, idx_name):
    for index in indexes:
        if idx_name == index.name:
            return True

    return False


def upgrade(migrate_engine):
    meta = MetaData()
    meta.bind = migrate_engine

    jobs = Table('jobs', meta, autoload=True)

    if not _has_index(jobs.indexes, INDEX_STATUS_NAME):
        index = Index(INDEX_STATUS_NAME, jobs.c.status)
        index.create(migrate_engine)
    else:
        LOG.info(_('Index %s already exists.') % INDEX_STATUS_NAME)

    if not _has_index(jobs.indexes, INDEX_TIMEOUT_NAME):
        index = Index(INDEX_TIMEOUT_NAME, jobs.c.timeout)
        index.create(migrate_engine)
    else:
        LOG.info(_('Index %s already exists.') % INDEX_TIMEOUT_NAME)


def downgrade(migrate_engine):
    meta = MetaData()
    meta.bind = migrate_engine

    jobs = Table('jobs', meta, autoload=True)

    index = Index(INDEX_STATUS_NAME, jobs.c.status)
    index.drop(migrate_engine)

    index = Index(INDEX_TIMEOUT_NAME, jobs.c.timeout)
    index.drop(migrate_engine)
