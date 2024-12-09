# Copyright (c) 2023 Airbyte, Inc., all rights reserved.
"""Cloud Workspace integration tests.

These tests are designed to be run against a running instance of the Airbyte API.
"""

from __future__ import annotations

import airbyte as ab
from airbyte.cloud import CloudWorkspace
from airbyte.cloud.connections import CloudConnection
from airbyte.cloud.connectors import CloudSource


def test_deploy_destination(
    cloud_workspace: CloudWorkspace,
    deployable_dummy_destination: ab.Destination,
) -> None:
    """Test deploying a source to a workspace."""
    cloud_destination = cloud_workspace.deploy_destination(
        name="test-destination",
        destination=deployable_dummy_destination,
        random_name_suffix=True,
    )
    cloud_workspace.permanently_delete_destination(cloud_destination)


def test_deploy_source(
    cloud_workspace: CloudWorkspace,
) -> None:
    """Test deploying a source to a workspace."""
    source = ab.get_source(
        "source-faker",
        config={"count": 100},
    )
    source.check()
    cloud_source: CloudSource = cloud_workspace.deploy_source(
        name="test-source",
        source=source,
    )
    cloud_workspace.permanently_delete_source(cloud_source)


def test_deploy_connection(
    cloud_workspace: CloudWorkspace,
    deployable_dummy_source,
    deployable_dummy_destination,
) -> None:
    """Test deploying a source and cache to a workspace as a new connection."""
    cloud_source = cloud_workspace.deploy_source(
        name="test-source",
        source=deployable_dummy_source,
        random_name_suffix=True,
    )
    cloud_destination = cloud_workspace.deploy_destination(
        name="test-destination",
        destination=deployable_dummy_destination,
        random_name_suffix=True,
    )

    connection: CloudConnection = cloud_workspace.deploy_connection(
        connection_name="test-connection",
        source=cloud_source,
        destination=cloud_destination,
    )
    # assert set(connection.stream_names) == set(["users", "products", "purchases"])
    # assert connection.table_prefix == "abc_deleteme_"
    cloud_workspace.permanently_delete_connection(
        connection=connection,
        cascade_delete_source=True,
        cascade_delete_destination=True,
    )
