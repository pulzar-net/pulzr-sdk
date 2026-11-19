"""Device types: the codec library, its history, and deploying a version."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .._client import compact, path
from . import Resource

_BASE = '/api/v1/device-types'


class DeviceTypes(Resource):
    def list(self) -> List[Dict[str, Any]]:
        """Every type Pulzar publishes plus the org's own."""
        return self._client.request('GET', _BASE)['result']

    def versions(self, device_type_id: str) -> List[Dict[str, Any]]:
        """The codec's commits, newest first; metadata only."""
        return self._client.request('GET', path(_BASE, device_type_id, 'versions'))['result']

    def version(self, device_type_id: str, oid: str = 'HEAD') -> Dict[str, Any]:
        """One commit with its source and test vectors; `HEAD` is the tip."""
        return self._client.request('GET', path(_BASE, device_type_id, 'versions', oid))

    def deploy(self, device_type_id: str, *, device_profile_id: Optional[str] = None,
               commit: Optional[str] = None) -> Dict[str, Any]:
        """Org admin. Make a codec version live: into a device profile for a
        LoRaWAN type (`device_profile_id` required), or for every beacon of a
        Bluetooth type. `commit` defaults to the tip."""
        return self._client.request('POST', path(_BASE, device_type_id, 'deploy'),
                                    json=compact(deviceProfileId=device_profile_id, commit=commit))

    def set_quantities(self, device_type_id: str,
                       mapping: Dict[str, Optional[Dict[str, Any]]]) -> Dict[str, Any]:
        """Org admin. Map codec fields to canonical quantities:
        `{'temp': {'quantity': 'temperature', 'unit': '°F'}}`; None removes a
        field's mapping. Fields not named are left as they are."""
        return self._client.request('PUT', path(_BASE, device_type_id, 'quantities'),
                                    json=mapping)

    def set_value_aliases(self, device_type_id: str,
                          aliases: Optional[Dict[str, Dict[str, str]]]) -> Dict[str, Any]:
        """Org admin. Declare text values the codec has renamed,
        `{'type': {'OLD': 'NEW'}}`, so filters match uplinks stored under
        either spelling. Replaces the whole set; None clears it."""
        return self._client.request('PATCH', path(_BASE, device_type_id),
                                    json={'valueAliases': aliases})
