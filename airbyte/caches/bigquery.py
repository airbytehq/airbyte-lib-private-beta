# Copyright (c) 2024 Airbyte, Inc., all rights reserved.

"""A BigQuery implementation of the cache."""

import urllib

# if TYPE_CHECKING:
from pathlib import Path
from typing import TYPE_CHECKING, final

import pandas as pd
import pandas_gbq
import pyarrow as pa
import sqlalchemy
from google.oauth2 import service_account
from overrides import overrides

from airbyte import exceptions as exc
from airbyte._processors.file import ParquetWriter, ParquetWriterConfig
from airbyte.caches.base import (
    SQLCacheBase,
    SQLCacheConfigBase,
)
from airbyte.telemetry import CacheTelemetryInfo
from airbyte.types import SQLTypeConverter


if TYPE_CHECKING:
    from sqlalchemy.engine.reflection import Inspector


class BigQueryCacheConfig(SQLCache):
    """Configuration for the BigQuery cache.

    Also inherits config from the ParquetWriter, which is responsible for writing files to disk.
    """

    project: str
    credentials_path: str

    # Already defined in base class:
    # schema_name: str

    @overrides
    def get_sql_alchemy_url(self) -> str:
        """Return the SQLAlchemy URL to use."""
        credentials_path_encoded = urllib.parse.quote(self.credentials_path)
        return f"bigquery://{self.project!s}?credentials_path={credentials_path_encoded}"


    def get_database_name(self) -> str:
        """Return the name of the database. For BigQuery, this is the schema/dataset name."""
        return self.schema_name

class BigQueryConverter(SQLTypeConverter):
    """A class to convert types for BigQuery."""


    @overrides
    def to_sql_type(
        self,
        json_schema_property_def: dict[str, str | dict | list],
    ) -> sqlalchemy.types.TypeEngine:
        """Convert a value to a SQL type.

        We first call the parent class method to get the type. Then if the type is VARCHAR or BIGINT, we
        replace it with respective BigQuery types.
        """
        sql_type = super().to_sql_type(json_schema_property_def)
        # to-do: replace hardcoded return types with some sort of snowflake Variant equivalent
        if isinstance(sql_type, sqlalchemy.types.VARCHAR):
            return "String"
        if isinstance(sql_type, sqlalchemy.types.BIGINT):
            return "INT64"

        return sql_type.__class__.__name__


class BigQuerySqlProcessor(SqlProcessorBase):
    """A BigQuery implementation of the cache.
    """

    config_class = BigQueryCacheConfig
    file_writer_class = ParquetWriter
    type_converter_class = BigQueryConverter

    @final
    @overrides
    def _fully_qualified(
        self,
        table_name: str,
    ) -> str:
        """Return the fully qualified name of the given table."""
        return f"`{self.config.schema_name}.{table_name!s}`"

    @final
    @overrides
    def _quote_identifier(self, identifier: str) -> str:
        """Return the identifier name as is. BigQuery does not require quoting identifiers"""
        return f'{identifier}'

    @final
    @overrides
    def get_telemetry_info(self) -> CacheTelemetryInfo:
        return CacheTelemetryInfo("bigquery")

    def _write_files_to_new_table(
        self,
        files: list[Path],
        stream_name: str,
        batch_id: str,
    ) -> str:
        """Write a file(s) to a new table.

        This is a generic implementation, which can be overridden by subclasses
        to improve performance.
        """
        temp_table_name = self._create_table_for_loading(stream_name, batch_id)
        for file_path in files:
            with pa.parquet.ParquetFile(file_path) as pf:
                record_batch = pf.read()
                dataframe = record_batch.to_pandas()

                # Pandas will auto-create the table if it doesn't exist, which we don't want.
                if not self._table_exists(temp_table_name):
                    raise exc.AirbyteLibInternalError(
                        message="Table does not exist after creation.",
                        context={
                            "temp_table_name": temp_table_name,
                        },
                    )

                credentials = service_account.Credentials.from_service_account_file(self.config.credentials_path)

                # timestamp columns need to be converted to datetime to work with pandas_gbq
                # to-do: generalize the following to all columns of column type. This change is to test specically with faker source.
                dataframe['created_at'] = pd.to_datetime(dataframe['created_at'])
                dataframe['updated_at'] = pd.to_datetime(dataframe['updated_at'])

                print(dataframe)

                pandas_gbq.to_gbq(
                    dataframe=dataframe,
                    destination_table=f"airbyte_raw.{temp_table_name}",
                    project_id="dataline-integration-testing",
                    if_exists="append",
                    credentials=credentials,
                    # table_schema=columns_definition_gbq
                )
        return temp_table_name

    @final
    @overrides
    def _get_tables_list(
        self,
        ) -> list[str]:
        """
        For bigquery, {schema_name}.{table_name} is returned, so we need to
        strip the schema name in front of the table name, if it exists.
        """
        with self.get_sql_connection() as conn:
            inspector: Inspector = sqlalchemy.inspect(conn)
            tables = inspector.get_table_names(schema=self.config.schema_name)
            schema_prefix = f"{self.config.schema_name}."
            tables = [table.replace(schema_prefix, '', 1) if table.startswith(schema_prefix) else table for table in tables]
            return tables
