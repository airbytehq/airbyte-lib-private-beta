# Copyright (c) 2023 Airbyte, Inc., all rights reserved.
"""These internal functions are used to interact with the Airbyte API (module named `airbyte`).

In order to insulate users from breaking changes and to avoid general confusion around naming
and design inconsistencies, we do not expose these functions or other Airbyte API classes within
PyAirbyte. Classes and functions from the Airbyte API external library should always be wrapped in
PyAirbyte classes - unless there's a very compelling reason to surface these models intentionally.

Similarly, modules outside of this file should try to avoid interfacing with `airbyte_api` library
directly. This will ensure a single source of truth when mapping between the `airbyte` and
`airbyte_api` libraries.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, Callable

import airbyte_api
import requests
from airbyte_api import api, models

from airbyte import exceptions as exc
from airbyte.exceptions import (
    AirbyteConnectionSyncError,
    AirbyteError,
    AirbyteMissingResourceError,
    AirbyteMultipleResourcesError,
)


if TYPE_CHECKING:
    from collections.abc import Iterable

    from airbyte.cloud.constants import ConnectorTypeEnum


JOB_WAIT_INTERVAL_SECS = 2.0
JOB_WAIT_TIMEOUT_SECS_DEFAULT = 60 * 60  # 1 hour
CLOUD_API_ROOT = "https://api.airbyte.com/v1"
LEGACY_API_ROOT = "https://cloud.airbyte.com/api/v1"

# Helper functions


def status_ok(status_code: int) -> bool:
    """Check if a status code is OK."""
    return status_code >= 200 and status_code < 300  # noqa: PLR2004  # allow inline magic numbers


def get_airbyte_server_instance(
    *,
    api_key: str,
    api_root: str,
) -> airbyte_api.Airbyte:
    """Get an Airbyte instance."""
    return airbyte_api.AirbyteAPI(
        security=models.Security(
            bearer_auth=api_key,
        ),
        server_url=api_root,
    )


# Get workspace


def get_workspace(
    workspace_id: str,
    *,
    api_root: str,
    api_key: str,
) -> models.WorkspaceResponse:
    """Get a connection."""
    airbyte_instance = get_airbyte_server_instance(
        api_key=api_key,
        api_root=api_root,
    )
    response = airbyte_instance.workspaces.get_workspace(
        api.GetWorkspaceRequest(
            workspace_id=workspace_id,
        ),
    )
    if status_ok(response.status_code) and response.workspace_response:
        return response.workspace_response

    raise AirbyteMissingResourceError(
        resource_type="workspace",
        context={
            "workspace_id": workspace_id,
            "response": response,
        },
    )


# List, get, and run connections


def list_connections(
    workspace_id: str,
    *,
    name_filter: str | Callable[[str], bool] | None = None,
    api_root: str,
    api_key: str,
) -> Iterable[api.ConnectionResponse]:
    """Get a connection.

    If name_filter is a string, only connections containing that name will be returned. If
    name_filter is a function, it will be called with the connection name and should return a
    boolean.
    """
    airbyte_instance = get_airbyte_server_instance(
        api_key=api_key,
        api_root=api_root,
    )
    offset = 0
    limit = 50

    if isinstance(name_filter, str):
        # Redefine name_filter as a function

        def name_filter(name: str) -> bool:
            return name_filter in name

    while True:
        response = airbyte_instance.connections.list_connections(
            api.ListConnectionsRequest(
                workspace_ids=[workspace_id],
                include_deleted=False,
                limit=limit,
                offset=offset,
            ),
        )

        if status_ok(response.status_code) and response.connections_response:
            connections = response.connections_response.data
            if not connections:
                # No more connections to list
                break

            for connection in connections:
                if name_filter is None or name_filter(connection.name):
                    yield connection

            offset += limit
        else:
            raise AirbyteError(
                context={
                    "workspace_id": workspace_id,
                    "response": response,
                }
            )


def get_connection(
    workspace_id: str,
    connection_id: str,
    *,
    api_root: str,
    api_key: str,
) -> api.ConnectionResponse:
    """Get a connection."""
    _ = workspace_id  # Not used (yet)
    airbyte_instance = get_airbyte_server_instance(
        api_key=api_key,
        api_root=api_root,
    )
    response = airbyte_instance.connections.get_connection(
        api.GetConnectionRequest(
            connection_id=connection_id,
        ),
    )
    if status_ok(response.status_code) and response.connection_response:
        return response.connection_response

    raise AirbyteMissingResourceError(connection_id, "connection", response.text)


def run_connection(
    workspace_id: str,
    connection_id: str,
    *,
    api_root: str,
    api_key: str,
) -> api.ConnectionResponse:
    """Get a connection.

    If block is True, this will block until the connection is finished running.

    If raise_on_failure is True, this will raise an exception if the connection fails.
    """
    _ = workspace_id  # Not used (yet)
    airbyte_instance = get_airbyte_server_instance(
        api_key=api_key,
        api_root=api_root,
    )
    response = airbyte_instance.jobs.create_job(
        models.JobCreateRequest(
            connection_id=connection_id,
            job_type=models.JobTypeEnum.SYNC,
        ),
    )
    if status_ok(response.status_code) and response.job_response:
        return response.job_response

    raise AirbyteConnectionSyncError(
        connection_id=connection_id,
        context={
            "workspace_id": workspace_id,
        },
        response=response,
    )


# Get job info (logs)


def get_job_logs(
    workspace_id: str,
    connection_id: str,
    limit: int = 20,
    *,
    api_root: str,
    api_key: str,
) -> list[api.JobResponse]:
    """Get a job's logs."""
    airbyte_instance = get_airbyte_server_instance(
        api_key=api_key,
        api_root=api_root,
    )
    response: api.ListJobsResponse = airbyte_instance.jobs.list_jobs(
        api.ListJobsRequest(
            workspace_ids=[workspace_id],
            connection_id=connection_id,
            limit=limit,
        ),
    )
    if status_ok(response.status_code) and response.jobs_response:
        return response.jobs_response.data

    raise AirbyteMissingResourceError(
        response=response,
        resource_type="job",
        context={
            "workspace_id": workspace_id,
            "connection_id": connection_id,
        },
    )


def get_job_info(
    job_id: str,
    *,
    api_root: str,
    api_key: str,
) -> api.JobResponse:
    """Get a job."""
    airbyte_instance = get_airbyte_server_instance(
        api_key=api_key,
        api_root=api_root,
    )
    response = airbyte_instance.jobs.get_job(
        api.GetJobRequest(
            job_id=job_id,
        ),
    )
    if status_ok(response.status_code) and response.job_response:
        return response.job_response

    raise AirbyteMissingResourceError(job_id, "job", response.text)


# Create, get, and delete sources


def create_source(
    name: str,
    *,
    workspace_id: str,
    config: dict[str, Any],
    api_root: str,
    api_key: str,
) -> api.SourceResponse:
    """Get a connection."""
    airbyte_instance = get_airbyte_server_instance(
        api_key=api_key,
        api_root=api_root,
    )
    response: api.CreateSourceResponse = airbyte_instance.sources.create_source(
        models.SourceCreateRequest(
            name=name,
            workspace_id=workspace_id,
            configuration=config,  # TODO: wrap in a proper configuration object
            definition_id=None,  # Not used alternative to config.sourceType.
            secret_id=None,  # For OAuth, not yet supported
        ),
    )
    if status_ok(response.status_code) and response.source_response:
        return response.source_response

    raise AirbyteError(
        message="Could not create source.",
        response=response,
    )


def get_source(
    source_id: str,
    *,
    api_root: str,
    api_key: str,
) -> api.SourceResponse:
    """Get a connection."""
    airbyte_instance = get_airbyte_server_instance(
        api_key=api_key,
        api_root=api_root,
    )
    response = airbyte_instance.sources.get_source(
        api.GetSourceRequest(
            source_id=source_id,
        ),
    )
    if status_ok(response.status_code) and response.connection_response:
        return response.connection_response

    raise AirbyteMissingResourceError(source_id, "source", response.text)


def delete_source(
    source_id: str,
    *,
    api_root: str,
    api_key: str,
    workspace_id: str | None = None,
) -> None:
    """Delete a source."""
    _ = workspace_id  # Not used (yet)
    airbyte_instance = get_airbyte_server_instance(
        api_key=api_key,
        api_root=api_root,
    )
    response = airbyte_instance.sources.delete_source(
        api.DeleteSourceRequest(
            source_id=source_id,
        ),
    )
    if not status_ok(response.status_code):
        raise AirbyteError(
            context={
                "source_id": source_id,
                "response": response,
            },
        )


# Create, get, and delete destinations


def create_destination(
    name: str,
    *,
    workspace_id: str,
    config: dict[str, Any],
    api_root: str,
    api_key: str,
) -> api.DestinationResponse:
    """Get a connection."""
    airbyte_instance = get_airbyte_server_instance(
        api_key=api_key,
        api_root=api_root,
    )
    response: api.CreateDestinationResponse = airbyte_instance.destinations.create_destination(
        models.DestinationCreateRequest(
            name=name,
            workspace_id=workspace_id,
            configuration=config,  # TODO: wrap in a proper configuration object
        ),
    )
    if status_ok(response.status_code) and response.destination_response:
        return response.destination_response

    raise AirbyteError(
        message="Could not create destination.",
        response=response,
    )


def get_destination(
    destination_id: str,
    *,
    api_root: str,
    api_key: str,
) -> api.DestinationResponse:
    """Get a connection."""
    airbyte_instance = get_airbyte_server_instance(
        api_key=api_key,
        api_root=api_root,
    )
    response = airbyte_instance.destinations.get_destination(
        api.GetDestinationRequest(
            destination_id=destination_id,
        ),
    )
    if status_ok(response.status_code):
        # TODO: This is a temporary workaround to resolve an issue where
        # the destination API response is of the wrong type.
        raw_response: dict[str, Any] = json.loads(response.raw_response.text)
        raw_configuration: dict[str, Any] = raw_response["configuration"]
        destination_type = raw_response.get("destinationType")
        if destination_type == "snowflake":
            response.destination_response.configuration = models.DestinationSnowflake.from_dict(
                raw_configuration,
            )
        if destination_type == "bigquery":
            response.destination_response.configuration = models.DestinationBigquery.from_dict(
                raw_configuration,
            )
        if destination_type == "postgres":
            response.destination_response.configuration = models.DestinationPostgres.from_dict(
                raw_configuration,
            )
        if destination_type == "duckdb":
            response.destination_response.configuration = models.DestinationDuckdb.from_dict(
                raw_configuration,
            )

        return response.destination_response

    raise AirbyteMissingResourceError(destination_id, "destination", response.text)


def delete_destination(
    destination_id: str,
    *,
    api_root: str,
    api_key: str,
    workspace_id: str | None = None,
) -> None:
    """Delete a destination."""
    _ = workspace_id  # Not used (yet)
    airbyte_instance = get_airbyte_server_instance(
        api_key=api_key,
        api_root=api_root,
    )
    response = airbyte_instance.destinations.delete_destination(
        api.DeleteDestinationRequest(
            destination_id=destination_id,
        ),
    )
    if not status_ok(response.status_code):
        raise AirbyteError(
            context={
                "destination_id": destination_id,
                "response": response,
            },
        )


# Create and delete connections

def create_connection(
    name: str,
    *,
    source_id: str,
    destination_id: str,
    api_root: str,
    api_key: str,
    workspace_id: str | None = None,
    prefix: str,
    selected_stream_names: list[str] | None = None,
) -> models.ConnectionResponse:
    _ = workspace_id  # Not used (yet)
    airbyte_instance = get_airbyte_server_instance(
        api_key=api_key,
        api_root=api_root,
    )
    stream_configurations: models.StreamConfigurations | None = None
    if selected_stream_names:
        stream_configuration_list = []
        for stream_name in selected_stream_names:
            stream_configuration = models.StreamConfiguration(
                name=stream_name,
            )
            stream_configuration_list.append(stream_configuration)

        stream_configurations = models.StreamConfigurations(stream_configuration_list)

    response = airbyte_instance.connections.create_connection(
        models.ConnectionCreateRequest(
            name=name,
            source_id=source_id,
            destination_id=destination_id,
            configurations=stream_configurations,
            prefix=prefix,
        ),
    )
    if not status_ok(response.status_code):
        raise AirbyteError(
            context={
                "source_id": source_id,
                "destination_id": destination_id,
                "response": response,
            },
        )

    return response.connection_response


def get_connection_by_name(
    workspace_id: str,
    connection_name: str,
    *,
    api_root: str,
    api_key: str,
) -> models.ConnectionResponse:
    """Get a connection."""
    connections = list_connections(
        workspace_id=workspace_id,
        api_key=api_key,
        api_root=api_root,
    )
    found: list[models.ConnectionResponse] = [
        connection for connection in connections if connection.name == connection_name
    ]
    if len(found) == 0:
        raise AirbyteMissingResourceError(
            connection_name, "connection", f"Workspace: {workspace_id}"
        )

    if len(found) > 1:
        raise AirbyteMultipleResourcesError(
            resource_type="connection",
            resource_name_or_id=connection_name,
            context={
                "workspace_id": workspace_id,
                "multiples": found,
            },
        )

    return found[0]


def delete_connection(
    connection_id: str,
    api_root: str,
    workspace_id: str,
    api_key: str,
) -> None:
    _ = workspace_id  # Not used (yet)
    airbyte_instance = get_airbyte_server_instance(
        api_key=api_key,
        api_root=api_root,
    )
    response = airbyte_instance.connections.delete_connection(
        api.DeleteConnectionRequest(
            connection_id=connection_id,
        ),
    )
    if not status_ok(response.status_code):
        raise AirbyteError(
            context={
                "connection_id": connection_id,
                "response": response,
            },
        )


# Legacy API Functions


def _transform_legacy_api_root(api_root: str) -> str:
    """Transform the API root to the legacy API root if needed."""
    if api_root == CLOUD_API_ROOT:
        # We know the user is using Airbyte Cloud, so we can safely return the legacy API root.
        return LEGACY_API_ROOT

    # TODO: Figure out how to translate an OSS/Enterprise API root to the legacy Config API root.
    raise NotImplementedError(
        "Airbyte OSS and Enterprise are not currently supported for this operation."
    )


def check_connector_config(
    connector_id: str,
    connector_type: ConnectorTypeEnum,
    workspace_id: str,
    *,
    api_key: str,
    api_root: str,
) -> None:
    """Check source or destination with its current config.

    Raises `AirbyteConnectorCheckFailedError` if the check fails.

    This calls the Config API because the Airbyte API does not support this operation.

    Equivalent to:

    ```bash
    curl -X POST "https://cloud.airbyte.com/api/v1/sources/check_connection" \
        -H "accept: application/json"\
        -H "content-type: application/json" \
        -d '{"sourceId":"18efe99a-7400-4000-8d95-ca2cb0e7b401"}'
    ```

    API Docs:
        https://airbyte-public-api-docs.s3.us-east-2.amazonaws.com/rapidoc-api-docs.html#post-/v1/sources/check_connection
    """
    legacy_api_root = _transform_legacy_api_root(api_root)

    _ = workspace_id  # Not used
    response: requests.Response = requests.post(
        f"{legacy_api_root}/{connector_type.value}s/check_connection",
        headers={
            "accept": "application/json",
            "content-type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        json={
            f"{connector_type.value}Id": connector_id,
        },
    )
    response.raise_for_status()

    response_json = response.json()
    if not response_json.get("status", None) == "succeeded":
        raise exc.AirbyteConnectorCheckFailedError(
            message=response_json.get("message", None),
            context=response_json,
        )
