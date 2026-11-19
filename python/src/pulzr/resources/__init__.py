"""One module per area of the API; each is an attribute of `Client`."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .._client import Client


class Resource:
    def __init__(self, client: 'Client') -> None:
        self._client = client
