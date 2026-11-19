"""Gateways: the org's own, what they hear, and operating them.

What a call may do is the caller's rights on that gateway: a gateways:read
key reads the org's gateways; restarting, updating, offering or removing one
needs gateways:write and org:admin. Shells and a gateway's web interface are
not in the API -- they are opened by a person in the console.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .._client import compact, path
from . import Resource


class Gateways(Resource):
    def list(self) -> List[Dict[str, Any]]:
        """The org's gateways, and community ones on its map. Each carries
        `can`: what this credential may do to it."""
        return self._client.request('GET', '/api/v1/gateways')['result']

    def models(self) -> List[Dict[str, Any]]:
        return self._client.request('GET', '/api/v1/gateways/models')['result']

    def metrics(self, gateway_id: str, *, hours: Optional[int] = None,
                aggregation: Optional[str] = None) -> Dict[str, Any]:
        """The LNS's traffic counts for one gateway."""
        return self._client.request('GET', path('/api/v1/gateways', gateway_id, 'metrics'),
                                    params={'hours': hours, 'aggregation': aggregation})

    def devices(self, gateway_id: str, *, days: Optional[int] = None) -> Dict[str, Any]:
        """Devices it heard (`result`) and devices in its tenant never heard
        by anything (`silent`)."""
        return self._client.request('GET', path('/api/v1/gateways', gateway_id, 'devices'),
                                    params={'days': days})

    def status(self, gateway_id: str) -> Dict[str, Any]:
        """Asks the gateway itself, over its management link."""
        return self._client.request('GET', path('/api/v1/gateway-ops', gateway_id, 'status'))

    def backhaul(self, gateway_id: str) -> Dict[str, Any]:
        """Tunnel and SIM, and which path a connection would take. Never
        touches the gateway."""
        return self._client.request('GET', path('/api/v1/gateway-ops', gateway_id, 'backhaul'))

    def network(self, gateway_id: str) -> Dict[str, Any]:
        """Which network its tunnel and SIM are on: the org's own or
        Pulzar's. Never touches the gateway."""
        return self._client.request('GET', path('/api/v1/gateways', gateway_id, 'network'))

    def sim(self, gateway_id: str) -> Dict[str, Any]:
        return self._client.request('GET', path('/api/v1/gateway-ops', gateway_id, 'sim'))

    def firmware(self, gateway_id: str) -> Dict[str, Any]:
        return self._client.request('GET', path('/api/v1/gateway-ops', gateway_id, 'firmware'))

    def restart(self, gateway_id: str) -> Dict[str, Any]:
        """Restart the packet forwarder."""
        return self._client.request('POST', path('/api/v1/gateway-ops', gateway_id, 'restart'))

    def reset_sim(self, gateway_id: str) -> Dict[str, Any]:
        """Force the SIM to re-attach. The cellular link drops for up to a minute."""
        return self._client.request('POST', path('/api/v1/gateway-ops', gateway_id, 'sim', 'reset'))

    def update_firmware(self, gateway_id: str, tag: str, *,
                        over_cellular: bool = False) -> Dict[str, Any]:
        """Install a PulzarOS release. On a SIM, `over_cellular` must say so."""
        return self._client.request('POST', path('/api/v1/gateway-ops', gateway_id, 'firmware'),
                                    json={'tag': tag, 'overCellular': over_cellular})

    def remove(self, gateway_id: str) -> Dict[str, Any]:
        """Delete its identity, LNS record and configuration. Cannot be undone."""
        return self._client.request('DELETE', path('/api/v1/gateway-ops/gateways', gateway_id))

    def offer(self, gateway_id: str, to_org: str, *, confirm: str,
              note: Optional[str] = None) -> Dict[str, Any]:
        """Offer it to another org (by alias); `confirm` repeats the EUI.
        Nothing moves until that org accepts."""
        return self._client.request(
            'POST', path('/api/v1/gateway-ops/gateways', gateway_id, 'transfer'),
            json=compact(toOrg=to_org, confirm=confirm, note=note))

    def transfers(self) -> List[Dict[str, Any]]:
        """Offers to and from the org, newest first."""
        return self._client.request('GET', '/api/v1/gateway-ops/transfers')['result']

    def accept(self, transfer_id: str, *, confirm: str) -> Dict[str, Any]:
        return self._client.request(
            'POST', path('/api/v1/gateway-ops/transfers', transfer_id, 'accept'),
            json={'confirm': confirm})

    def decline(self, transfer_id: str) -> Dict[str, Any]:
        return self._client.request(
            'POST', path('/api/v1/gateway-ops/transfers', transfer_id, 'decline'))

    def cancel(self, transfer_id: str) -> Dict[str, Any]:
        return self._client.request(
            'POST', path('/api/v1/gateway-ops/transfers', transfer_id, 'cancel'))
