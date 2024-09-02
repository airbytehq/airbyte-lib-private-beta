# Copyright (c) 2024 Airbyte, Inc., all rights reserved.
"""Write interfaces for PyAirbyte."""

from __future__ import annotations

import abc
from typing import IO, TYPE_CHECKING


if TYPE_CHECKING:
    from airbyte._future_cdk.catalog_providers import CatalogProvider
    from airbyte._future_cdk.state_writers import StateWriterBase
    from airbyte._message_iterators import AirbyteMessageIterator
    from airbyte.progress import ProgressTracker
    from airbyte.strategies import WriteStrategy


class AirbyteWriterInterface(abc.ABC):
    """An interface for writing Airbyte messages."""

    @property
    def name(self) -> str:
        """Return the name of the writer.

        This is used for logging and state tracking.
        """
        return self.__class__.__name__

    def _write_airbyte_io_stream(
        self,
        stdin: IO[str],
        *,
        catalog_provider: CatalogProvider,
        write_strategy: WriteStrategy,
        state_writer: StateWriterBase | None = None,
        progress_tracker: ProgressTracker,
    ) -> None:
        """Read from the connector and write to the cache.

        This is a specialized version of `_write_airbyte_message_stream` that reads from an IO
        stream. Writers can override this method to provide custom behavior for reading from an IO
        stream, without paying the cost of converting the stream to an AirbyteMessageIterator.
        """
        self._write_airbyte_message_stream(
            stdin,
            catalog_provider=catalog_provider,
            write_strategy=write_strategy,
            state_writer=state_writer,
            progress_tracker=progress_tracker,
        )

    @abc.abstractmethod
    def _write_airbyte_message_stream(
        self,
        stdin: IO[str] | AirbyteMessageIterator,
        *,
        catalog_provider: CatalogProvider,
        write_strategy: WriteStrategy,
        state_writer: StateWriterBase | None = None,
        progress_tracker: ProgressTracker,
    ) -> None:
        """Write the incoming data.

        Note: Callers should use `_write_airbyte_io_stream` instead of this method if
        `stdin` is always an IO stream. This ensures that the most efficient method is used for
        writing the incoming stream.
        """
        ...
