"""Canonical readings: one vocabulary of quantities across every vendor."""

from __future__ import annotations

from typing import Iterable, List, Optional, Union, cast

from ..types import LatestReadings, Quantity, Series
from . import Resource

Devices = Union[str, Iterable[str], None]


def _devices(value: Devices) -> Optional[str]:
    if value is None or isinstance(value, str):
        return value
    return ','.join(value)


class Readings(Resource):
    def latest(self, quantity: Optional[str] = None, *, channel: Optional[str] = None,
               devices: Devices = None, application_id: Optional[str] = None,
               device_type_id: Optional[str] = None) -> List[LatestReadings]:
        """Each device's newest readings. With `quantity`, only devices that
        have reported it, and its newest value however old."""
        data = self._client.request('GET', '/api/v1/readings/latest', params={
            'quantity': quantity, 'channel': channel, 'devices': _devices(devices),
            'applicationId': application_id, 'deviceTypeId': device_type_id,
        })
        return cast(List[LatestReadings], data['result'])

    def series(self, quantity: str, *, channel: Optional[str] = None,
               since: Optional[str] = None, interval: Optional[str] = None,
               aggregate: Optional[str] = None, group_by: Optional[str] = None,
               devices: Devices = None, application_id: Optional[str] = None) -> Series:
        """One quantity over time, bucketed. `since` is now-1h, now-6h,
        now-24h (default), now-7d, now-30d or now-90d; `aggregate` mean
        (default), min, max, last, count or sum; `group_by` none or device."""
        return cast(Series, self._client.request('GET', '/api/v1/readings', params={
            'quantity': quantity, 'channel': channel, 'from': since, 'interval': interval,
            'aggregate': aggregate, 'groupBy': group_by, 'devices': _devices(devices),
            'applicationId': application_id,
        }))


class Quantities(Resource):
    def list(self) -> List[Quantity]:
        """The catalog, with how many of the org's devices report each."""
        return cast(List[Quantity], self._client.request('GET', '/api/v1/quantities')['result'])

