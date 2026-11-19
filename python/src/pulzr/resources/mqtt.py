"""How to connect to the broker. Connecting is pulzr.mqtt."""

from __future__ import annotations

from typing import cast

from ..types import MqttConnection
from . import Resource


class Mqtt(Resource):
    def connection(self) -> MqttConnection:
        """Host, port, username and this org's topics. Needs `data:read`."""
        return cast(MqttConnection, self._client.request('GET', '/api/v1/mqtt/connection'))
