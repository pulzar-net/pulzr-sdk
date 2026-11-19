"""Airtime and fair use, and coverage: what the radio side of the network measured."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from .._client import compact, path
from . import Resource


class Airtime(Resource):
    def device(self, dev_eui: str, *, days: Optional[int] = None) -> Dict[str, Any]:
        """One device's time on air by UTC day (7 by default, today live)
        against its plan's fair-use policy, with its spreading factors."""
        return self._client.request('GET', path('/api/v1/devices', dev_eui, 'airtime'),
                                    params={'days': days})

    def day(self, day: Optional[str] = None, *, limit: Optional[int] = None) -> Dict[str, Any]:
        """The org's devices on one UTC day (YYYY-MM-DD, today by default),
        heaviest share of their allowance first. `exceeding` counts those over."""
        return self._client.request('GET', '/api/v1/airtime', params={'day': day, 'limit': limit})


class Coverage(Resource):
    def cells(self, *, gateway_id: Optional[str] = None, resolution: Optional[int] = None,
              bbox: Optional[Sequence[float]] = None) -> Dict[str, Any]:
        """The org's coverage as a GeoJSON FeatureCollection of H3 cells: the
        best gateway per cell, or one gateway's with `gateway_id`. `bbox` is
        (west, south, east, north)."""
        return self._client.request('GET', '/api/v1/coverage', params={
            'gatewayId': gateway_id, 'resolution': resolution,
            'bbox': ','.join(str(v) for v in bbox) if bbox else None,
        })

    def at(self, latitude: float, longitude: float) -> Dict[str, Any]:
        """Each gateway's signal where the org's devices were heard nearest a
        point. `heard` is False when nothing was measured near it."""
        return self._client.request('GET', '/api/v1/coverage/at',
                                    params={'latitude': latitude, 'longitude': longitude})

    def gateways(self) -> List[Dict[str, Any]]:
        return self._client.request('GET', '/api/v1/coverage/gateways')['result']

    def settings(self, *, public: Optional[bool] = None) -> Dict[str, Any]:
        """Whether the org shares its coverage publicly; pass `public` to
        change it (org admin)."""
        if public is None:
            return self._client.request('GET', '/api/v1/coverage/settings')
        return self._client.request('PUT', '/api/v1/coverage/settings', json={'public': public})

    def public(self, bbox: Sequence[float], *, resolution: Optional[int] = None) -> Dict[str, Any]:
        """The public layer: Pulzar-operated gateways only, from orgs that share."""
        return self._client.request('GET', '/api/v1/public/coverage', params={
            'bbox': ','.join(str(v) for v in bbox), 'resolution': resolution})

    def start_session(self, dev_eui: str) -> Dict[str, Any]:
        """Start a mapper session: positions sent with `add_fixes` are matched
        to the device's uplinks heard within 15 seconds of each."""
        return self._client.request('POST', '/api/v1/coverage/sessions', json={'devEui': dev_eui})

    def add_fixes(self, session_id: str, fixes: List[Dict[str, Any]]) -> Dict[str, Any]:
        """`fixes`: [{time, latitude, longitude, accuracy}], time ISO-8601 or
        epoch milliseconds, at most 120 per call."""
        return self._client.request('POST', path('/api/v1/coverage/sessions', session_id, 'fixes'),
                                    json={'fixes': [compact(**f) for f in fixes]})

    def stop_session(self, session_id: str) -> Dict[str, Any]:
        return self._client.request('POST', path('/api/v1/coverage/sessions', session_id, 'stop'))

    def sessions(self) -> List[Dict[str, Any]]:
        return self._client.request('GET', '/api/v1/coverage/sessions')['result']
