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

import os

from migrate import exceptions as versioning_exceptions
from migrate.versioning import api as versioning_api
from migrate.versioning import repository as versioning_repository
import sqlalchemy

from qonos.common import exception
from qonos.db.sqlalchemy import api as db_api
from qonos.openstack.common.gettextutils import _
import qonos.openstack.common.log as logging

LOG = logging.getLogger(__name__)

_REPOSITORY = None

get_engine = db_api.get_engine


def _check_and_init_version_control(meta):
    try:
        for table in ('schedules', 'schedule_metadata',
                      'jobs', 'job_metadata', 'job_faults',
                      'workers'):
            assert table in meta.tables

        # NOTE(venkatesh): if the existing db has already got the base tables,
        # set the version for migration to '6' as the first six version_scripts
        # are used for creating the base tables.
        return version_control(6)
    except AssertionError:
        msg = _("Unable to get the db_version. Reason: Unknown DB State.")
        raise exception.QonosException(msg)


def db_version():
    """
    Return the database's current migration number

    :retval version number
    """
    repository = _get_migrate_repo()
    try:
        return versioning_api.db_version(get_engine(), repository)
    except versioning_exceptions.DatabaseNotControlledError:
        meta = sqlalchemy.MetaData()
        engine = get_engine()
        meta.reflect(bind=engine)
        tables = meta.tables

        if len(tables) == 0:
            return version_control(0)
        else:
            return _check_and_init_version_control(meta)


def upgrade(version=None):
    """
    Upgrade the database's current migration level

    :param version: version to upgrade (defaults to latest)
    :retval version number
    """
    db_version()  # Ensure db is under migration control
    repository = _get_migrate_repo()
    version_str = version or 'latest'
    LOG.info(_("Upgrading database to version %s") % version_str)
    return versioning_api.upgrade(get_engine(), repository, version)


def downgrade(version):
    """
    Downgrade the database's current migration level

    :param version: version to downgrade to
    :retval version number
    """
    db_version()  # Ensure db is under migration control
    repository = _get_migrate_repo()
    LOG.info(_("Downgrading database to version %s") % version)
    return versioning_api.downgrade(get_engine(), repository, version)


def version_control(version=None):
    """
    Place a database under migration control
    """
    try:
        return _version_control(version)
    except versioning_exceptions.DatabaseAlreadyControlledError:
        msg = (_("database is already under migration control"))
        raise exception.DatabaseMigrationError(msg)


def _version_control(version):
    """
    Place a database under migration control

    This will only set the specific version of a database, it won't
    run any migrations.
    """
    repository = _get_migrate_repo()
    if version is None:
        version = repository.latest
    versioning_api.version_control(get_engine(), repository, version)
    return version


def db_sync(version=None):
    """
    Place a database under migration control and perform an upgrade

    :retval version number
    """
    if version is not None:
        try:
            version = int(version)
        except ValueError:
            raise exception.QonosException(_("version should be an integer"))

    current_version = int(db_version())
    if version is None or version > current_version:
        return upgrade(version=version)
    else:
        return downgrade(version=version)


def get_migrate_repo_path():
    """Get the path for the migrate repository."""
    path = os.path.join(os.path.abspath(os.path.dirname(__file__)),
                        'migrate_repo')
    assert os.path.exists(path)
    return path


def _get_migrate_repo():
    """Get the path for the migrate repository."""
    global _REPOSITORY
    if _REPOSITORY is None:
        _REPOSITORY = versioning_repository.Repository(get_migrate_repo_path())
    return _REPOSITORY
