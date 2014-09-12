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

from migrate.changeset.constraint import ForeignKeyConstraint
from sqlalchemy import MetaData, Table

from qonos.openstack.common.gettextutils import _
import qonos.openstack.common.log as logging


LOG = logging.getLogger(__name__)


def upgrade(migrate_engine):
    meta = MetaData()
    meta.bind = migrate_engine

    schedules = Table('schedules', meta, autoload=True)
    schedule_metadata = Table('schedule_metadata', meta, autoload=True)

    if not schedule_metadata.foreign_keys:
        cons = ForeignKeyConstraint([schedule_metadata.c.schedule_id],
                                    [schedules.c.id])
        cons.create()


def downgrade(migrate_engine):
    # Foreign key constraint may have been existing so not possible to
    # downgrade selectively. Downgrade can basically be just an NOP.
    LOG.info(_('Downgrade not required as foreign key '
               'may have been already existing'))
