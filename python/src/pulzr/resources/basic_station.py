"""LoRa Basics Station gateways: registering one, and its CUPS and LNS
credentials (net-api routes/basic_station.py).

`register` and `setup` return the credential files once; nothing can show
them again. Both, and `rotate` and `revoke`, need gateways:write and
org:admin; `status` needs gateways:read.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from .._client import compact, path
from . import Resource


class BasicStation(Resource):
    def register(self, gateway_id: str, name: str, *, auth: str = 'token') -> Dict[str, Any]:
        """Add a Basics Station gateway to the org and issue its bundle:
        `cupsUri`, `lnsUri` and `files` (`cups.trust`, `cups.key`, ...)."""
        return self._client.request('POST', '/api/v1/gateways/basic-station',
                                    json={'gatewayId': gateway_id, 'name': name, 'auth': auth})

    def status(self, gateway_id: str) -> Dict[str, Any]:
        """LNS connection, last CUPS check-in, and each credential's version."""
        return self._client.request('GET', path('/api/v1/gateways', gateway_id, 'basic-station'))

    def setup(self, gateway_id: str, *, auth: Optional[str] = None) -> Dict[str, Any]:
        """A new bundle for a gateway holding no working credentials."""
        return self._client.request('POST', path('/api/v1/gateways', gateway_id, 'basic-station', 'setup'),
                                    json=compact(auth=auth))

    def rotate(self, gateway_id: str) -> Dict[str, Any]:
        """New credentials over CUPS at the next check-in; the old ones work
        until the gateway uses the new."""
        return self._client.request('POST', path('/api/v1/gateways', gateway_id, 'basic-station', 'rotate'))

    def revoke(self, gateway_id: str, *, confirm: str) -> Dict[str, Any]:
        """Refuse every credential the gateway holds. `confirm` is its EUI."""
        return self._client.request('POST', path('/api/v1/gateways', gateway_id, 'basic-station', 'revoke'),
                                    json={'confirm': confirm})
