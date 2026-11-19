"""SIMs: the ones in the org's gateways, and on its own cellular network.

What a call may do is the caller's rights on that SIM, which each entry
carries as `can`: a gateways:read key reads the org's SIMs; changing or
resetting one needs gateways:write and org:admin. Other orgs' SIMs answer
404. A SIM's device web UI is not in the API; a person opens it in the
console.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from .._client import compact, path
from . import Resource


class Sims(Resource):
    def list(self, *, network: Optional[str] = None) -> Dict[str, Any]:
        """`result`: each SIM with its gateway and `can`; `orphaned`: the
        org's gateways bound to an ICCID the account no longer returns."""
        return self._client.request('GET', '/api/v1/sims', params={'network': network})

    def status(self, *, network: Optional[str] = None) -> Dict[str, Any]:
        """Whether each SIM is attached right now, by ICCID. Null is unknown."""
        return self._client.request('GET', '/api/v1/sims/status', params={'network': network})

    def usage(self, *, days: Optional[int] = None) -> Dict[str, Any]:
        """Daily remaining allowance across the org's SIMs, and its fall."""
        return self._client.request('GET', '/api/v1/sims/usage', params={'days': days})

    def get(self, iccid: str, *, network: Optional[str] = None) -> Dict[str, Any]:
        return self._client.request('GET', path('/api/v1/sims', iccid, 'detail'),
                                    params={'network': network})

    def billing(self, iccid: str, *, network: Optional[str] = None) -> Dict[str, Any]:
        return self._client.request('GET', path('/api/v1/sims', iccid, 'billing'),
                                    params={'network': network})

    def update(self, iccid: str, *, enabled: Optional[bool] = None,
               imei_lock: Optional[bool] = None, label: Optional[str] = None,
               network: Optional[str] = None) -> Dict[str, Any]:
        """Enable or disable it (disabling takes its gateway off cellular),
        lock it to its modem, or rename it. Only what is given changes."""
        return self._client.request('PATCH', path('/api/v1/sims', iccid),
                                    params={'network': network},
                                    json=compact(enabled=enabled, imeiLock=imei_lock, label=label))

    def reset(self, iccid: str, *, network: Optional[str] = None) -> Dict[str, Any]:
        """Force a re-attach. Its gateway is off cellular for up to a minute."""
        return self._client.request('POST', path('/api/v1/sims', iccid, 'reset'),
                                    params={'network': network})
