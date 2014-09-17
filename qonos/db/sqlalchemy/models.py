# vim: tabstop=4 shiftwidth=4 softtabstop=4

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
SQLAlchemy models for qonos data
"""

from sqlalchemy import Column, Integer, String, Index
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import ForeignKey, DateTime, Text
from sqlalchemy.orm import relationship, backref, object_mapper
from sqlalchemy import UniqueConstraint

from qonos.common import timeutils
from qonos.openstack.common import uuidutils

BASE = declarative_base()
COMMON_TABLE_ARGS = {
    'mysql_engine': 'InnoDB',
    'mysql_charset': 'utf8'
}


class ModelBase(object):
    """Base class for Qonos Models."""
    __table_args__ = COMMON_TABLE_ARGS
    __table_initialized__ = False

    created_at = Column(DateTime, default=timeutils.utcnow,
                        nullable=False)
    updated_at = Column(DateTime, default=timeutils.utcnow,
                        nullable=False, onupdate=timeutils.utcnow)
    id = Column(String(36), primary_key=True, default=uuidutils.generate_uuid)

    def save(self, session=None):
        """Save this object."""
        # import api here to prevent circular dependency problem
        import qonos.db.sqlalchemy.api as db_api
        session = session or db_api.get_session()
        session.add(self)
        session.flush()

    def delete(self, session=None):
        """Delete this object."""
        # import api here to prevent circular dependency problem
        import qonos.db.sqlalchemy.api as db_api
        session = session or db_api.get_session()
        session.delete(self)
        session.flush()

    def update(self, values):
        """dict.update() behaviour."""
        for k, v in values.iteritems():
            self[k] = v

    def __setitem__(self, key, value):
        setattr(self, key, value)

    def __getitem__(self, key):
        return getattr(self, key)

    def __iter__(self):
        self._i = iter(object_mapper(self).columns)
        return self

    def next(self):
        n = self._i.next().name
        return n, getattr(self, n)

    def keys(self):
        return self.__dict__.keys()

    def values(self):
        return self.__dict__.values()

    def items(self):
        return self.__dict__.items()

    def to_dict(self):
        return self.__dict__.copy()


class Schedule(BASE, ModelBase):
    """Represents a schedule in the datastore."""
    __tablename__ = 'schedules'
    __table_args__ = (Index('next_run_idx', 'next_run'),
                      COMMON_TABLE_ARGS)

    tenant = Column(String(255), nullable=False)
    action = Column(String(255), nullable=False)
    minute = Column(Integer, nullable=True)
    hour = Column(Integer, nullable=True)
    day_of_month = Column(Integer, nullable=True)
    month = Column(Integer, nullable=True)
    day_of_week = Column(Integer, nullable=True)
    last_scheduled = Column(DateTime, nullable=True)
    next_run = Column(DateTime, nullable=True, index=True)


class ScheduleMetadata(BASE, ModelBase):
    """Represents metadata of a schedule in the datastore."""
    __tablename__ = 'schedule_metadata'
    __table_args__ = (UniqueConstraint('schedule_id', 'key'),
                      COMMON_TABLE_ARGS)

    schedule_id = Column(String(36),
                         ForeignKey('schedules.id'), nullable=False)
    key = Column(String(255), nullable=False)
    value = Column(Text, nullable=False)
    parent = relationship(Schedule, backref=backref('schedule_metadata',
                                                    cascade='all,delete,'
                                                            'delete-orphan'))


class Worker(BASE, ModelBase):
    """Represents a worker in the datastore."""
    __tablename__ = 'workers'

    host = Column(String(255), nullable=False)
    process_id = Column(Integer, nullable=True)


class Job(BASE, ModelBase):
    """Represents a job in the datastore."""
    __tablename__ = 'jobs'
    __table_args__ = (Index('hard_timeout_idx', 'hard_timeout'),
                      COMMON_TABLE_ARGS)

    schedule_id = Column(String(36))
    tenant = Column(String(255), nullable=False)
    worker_id = Column(String(36), nullable=True)
    status = Column(String(255), default='QUEUED', nullable=False)
    action = Column(String(255), nullable=False)
    retry_count = Column(Integer, nullable=False, default=0)
    timeout = Column(DateTime, nullable=False)
    hard_timeout = Column(DateTime, nullable=False, index=True)
    version_id = Column(String(36))

    __mapper_args__ = {
        'version_id_col': version_id,
        'version_id_generator': lambda version: uuidutils.generate_uuid()
    }


class JobMetadata(BASE, ModelBase):
    """Represents job metadata in the datastore."""
    __tablename__ = 'job_metadata'
    __table_args__ = (UniqueConstraint('job_id', 'key'), COMMON_TABLE_ARGS)

    job_id = Column(String(36), ForeignKey('jobs.id'), nullable=False)
    key = Column(String(255), nullable=False)
    value = Column(Text, nullable=False)
    parent = relationship(Job, backref=backref('job_metadata',
                                               cascade='all,delete,'
                                                       'delete-orphan'))


class JobFault(BASE, ModelBase):
    """Represents a job fault in the datastore."""
    __tablename__ = 'job_faults'

    job_id = Column(String(36), nullable=False)
    schedule_id = Column(String(36), nullable=False)
    tenant = Column(String(255), nullable=False)
    worker_id = Column(String(36), nullable=False)
    action = Column(String(255), nullable=False)
    message = Column(String(255), nullable=True)
    job_metadata = Column(Text, nullable=True)


def register_models(engine):
    """
    Creates database tables for all models with the given engine.
    """
    models = (Schedule, ScheduleMetadata, Worker, Job, JobMetadata, JobFault)
    for model in models:
        model.metadata.create_all(engine)


def unregister_models(engine):
    """
    Drops database tables for all models with the given engine.
    """
    models = (Schedule, ScheduleMetadata, Worker, Job, JobMetadata, JobFault)
    for model in models:
        model.metadata.drop_all(engine)
