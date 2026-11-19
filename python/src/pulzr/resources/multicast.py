"""Multicast groups and relays (TS011)."""

from __future__ import annotations

import base64
from typing import Any, Dict, List, Optional, cast

from .._client import compact, path
from ..types import MulticastGroup, Relay
from . import Resource

_GROUPS = '/api/v1/multicast-groups'
_RELAYS = '/api/v1/relays'


class MulticastGroups(Resource):
    def list(self) -> List[MulticastGroup]:
        return cast(List[MulticastGroup], self._client.request('GET', _GROUPS)['result'])

    def create(self, name: str, application_id: str, region: str, *, group_type: str = 'C',
               dr: Optional[int] = None, frequency: Optional[int] = None,
               ping_slot_periodicity: Optional[int] = None) -> MulticastGroup:
        """The answer carries `keys`, and no later one does: they go on the
        devices out of band. `dr` and `frequency` default to the region's RX2."""
        body = compact(name=name, applicationId=application_id, region=region, groupType=group_type,
                       dr=dr, frequency=frequency, pingSlotPeriodicity=ping_slot_periodicity)
        return cast(MulticastGroup, self._client.request('POST', _GROUPS, json=body))

    def get(self, group_id: str) -> MulticastGroup:
        """With its `devices` and `gateways`; never its keys."""
        return cast(MulticastGroup, self._client.request('GET', path(_GROUPS, group_id)))

    def delete(self, group_id: str) -> None:
        self._client.request('DELETE', path(_GROUPS, group_id))

    def add_device(self, group_id: str, dev_eui: str) -> Dict[str, Any]:
        return self._client.request('POST', path(_GROUPS, group_id, 'devices'), json={'devEui': dev_eui})

    def remove_device(self, group_id: str, dev_eui: str) -> Dict[str, Any]:
        return self._client.request('DELETE', path(_GROUPS, group_id, 'devices', dev_eui))

    def add_gateway(self, group_id: str, gateway_id: str) -> Dict[str, Any]:
        return self._client.request('POST', path(_GROUPS, group_id, 'gateways'),
                                    json={'gatewayId': gateway_id})

    def remove_gateway(self, group_id: str, gateway_id: str) -> Dict[str, Any]:
        return self._client.request('DELETE', path(_GROUPS, group_id, 'gateways', gateway_id))

    def send(self, group_id: str, f_port: int, payload: bytes) -> Dict[str, Any]:
        """Queue one downlink for every member. `{fCnt}`."""
        return self._client.request('POST', path(_GROUPS, group_id, 'queue'), json={
            'fPort': f_port, 'data': base64.b64encode(payload).decode()})

    def queue(self, group_id: str) -> List[Dict[str, Any]]:
        return self._client.request('GET', path(_GROUPS, group_id, 'queue'))['result']

    def flush(self, group_id: str) -> None:
        self._client.request('DELETE', path(_GROUPS, group_id, 'queue'))


class Relays(Resource):
    def list(self) -> List[Relay]:
        return cast(List[Relay], self._client.request('GET', _RELAYS)['result'])

    def devices(self, relay_dev_eui: str) -> List[Dict[str, Any]]:
        return self._client.request('GET', path(_RELAYS, relay_dev_eui, 'devices'))['result']

    def add_device(self, relay_dev_eui: str, dev_eui: str) -> Dict[str, Any]:
        return self._client.request('POST', path(_RELAYS, relay_dev_eui, 'devices'),
                                    json={'devEui': dev_eui})

    def remove_device(self, relay_dev_eui: str, dev_eui: str) -> Dict[str, Any]:
        return self._client.request('DELETE', path(_RELAYS, relay_dev_eui, 'devices', dev_eui))
