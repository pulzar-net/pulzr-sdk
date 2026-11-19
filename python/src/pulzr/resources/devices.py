"""Devices: what is on the network, its readings, and sending to it."""

from __future__ import annotations

import base64
from typing import Any, Dict, List, Optional, Union

from .._client import compact, path
from . import Resource


class Devices(Resource):
    def __init__(self, client: Any) -> None:
        super().__init__(client)
        self.downlinks = Downlinks(client)
        self.commands = Commands(client)
        self.registry = Registry(client)
        self.transfers = Transfers(client)

    def list(self) -> List[Dict[str, Any]]:
        """Every device in the org that has reported, with whether it is
        online by its application's threshold. One that was registered and
        never heard from is not here."""
        return self._client.request('GET', '/api/v1/data/devices/health')['result']

    def get(self, dev_eui: str) -> Dict[str, Any]:
        """Everything stored about one device: latest uplink, decoded fields
        with their units, radio, location."""
        return self._client.request('GET', path('/api/v1/data/devices', dev_eui))

    def readings(self, dev_eui: str, *, since: Optional[str] = None,
                 limit: Optional[int] = None) -> Dict[str, Any]:
        """Recent uplinks with canonical readings beside the raw fields.
        `since` is one of now-1h, now-6h, now-24h (default), now-7d, now-30d,
        now-90d."""
        return self._client.request('GET', path('/api/v1/devices', dev_eui, 'readings'),
                                    params={'since': since, 'limit': limit})

    def location(self, dev_eui: str, *, history: Optional[int] = None) -> Dict[str, Any]:
        """Where a device is: `location.source` is `device` (its own fix),
        `manual` (set by hand), `solved` (from the gateways that heard it,
        with `accuracyM` and `method`) or `gateway`."""
        return self._client.request('GET', path('/api/v1/devices', dev_eui, 'location'),
                                    params={'history': history})

    def set_location(self, dev_eui: str, latitude: float, longitude: float) -> Dict[str, Any]:
        """Set where a device is by hand: a sensor mounted at a bay. Below the
        device's own fix, above a solved or gateway position."""
        return self._client.request('PUT', path('/api/v1/devices', dev_eui, 'location'),
                                    json={'latitude': latitude, 'longitude': longitude})

    def clear_location(self, dev_eui: str) -> None:
        """Clear a hand-set position."""
        self._client.request('DELETE', path('/api/v1/devices', dev_eui, 'location'))

    def provision(self, dev_eui: Optional[str] = None, *, app_key: Optional[str] = None,
                  device_profile: Optional[str] = None, join_eui: Optional[str] = None,
                  name: Optional[str] = None, application: Optional[str] = None,
                  tags: Optional[Dict[str, str]] = None, mac: Optional[str] = None,
                  device_type: Optional[str] = None, **extra: Any) -> Dict[str, Any]:
        """Register a device (org admin). LoRaWAN takes `dev_eui`, `app_key`
        and `device_profile`; a Bluetooth beacon takes `mac` and
        `device_type`. Registering a DevEUI this org already has updates it,
        so a retry after a timeout is safe."""
        body = compact(devEui=dev_eui, appKey=app_key, deviceProfile=device_profile,
                       joinEui=join_eui, name=name, application=application, tags=tags,
                       mac=mac, deviceType=device_type)
        body.update(extra)
        return self._client.request('POST', '/api/v1/provisioning/devices', json=body)

    def claim(self, dev_eui: Optional[str] = None, claim_code: Optional[str] = None, *,
              qr: Optional[str] = None, application: Optional[str] = None,
              device_profile: Optional[str] = None,
              name: Optional[str] = None) -> Dict[str, Any]:
        """Claim a device with the code on its label: `qr` (the TR005 text)
        or `dev_eui` and `claim_code`. Registered with keys nobody is shown.
        Wrong codes are counted; past the limit this raises with status 429."""
        body = compact(qr=qr, devEui=None if qr else dev_eui, claimCode=None if qr else claim_code,
                       application=application, deviceProfile=device_profile, name=name)
        return self._client.request('POST', '/api/v1/devices/claim', json=body)

    def release(self, dev_eui: str, *, confirm: str, app_key: Optional[str] = None,
                valid_days: Optional[int] = None) -> Dict[str, Any]:
        """Remove a device from the org and list it in the registry with a
        new claim code, returned here and nowhere else (org admin). `confirm`
        repeats the EUI. The AppKey is unchanged unless `app_key` gives the
        one the vendor's tool set."""
        return self._client.request('POST', path('/api/v1/devices', dev_eui, 'release'),
                                    json=compact(confirm=confirm, appKey=app_key,
                                                 validDays=valid_days))

    def decommission(self, dev_eui: str) -> Dict[str, Any]:
        """Remove a device (org admin). `removed` is False when it was already
        gone; that is not an error."""
        return self._client.request('DELETE', path('/api/v1/provisioning/devices', dev_eui))['result']


class Downlinks(Resource):
    """The LoRaWAN downlink queue. A Bluetooth device has none (409)."""

    def list(self, dev_eui: str) -> List[Dict[str, Any]]:
        return self._client.request('GET', path('/api/v1/devices', dev_eui, 'downlinks'))['result']

    def enqueue(self, dev_eui: str, f_port: int, *, data: Union[bytes, str, None] = None,
                object: Optional[Dict[str, Any]] = None,
                confirmed: bool = False) -> Dict[str, Any]:
        """Queue one downlink: `data` as bytes (or base64 text), or `object`
        for the device profile's codec to encode. Not both."""
        if isinstance(data, (bytes, bytearray)):
            data = base64.b64encode(bytes(data)).decode()
        body = compact(fPort=f_port, data=data, object=object, confirmed=confirmed)
        return self._client.request('POST', path('/api/v1/devices', dev_eui, 'downlinks'),
                                    json=body)

    def flush(self, dev_eui: str) -> Dict[str, Any]:
        """Drop everything queued. The LNS has no remove-one."""
        return self._client.request('DELETE', path('/api/v1/devices', dev_eui, 'downlinks'))


class Commands(Resource):
    """Named commands from the device type, encoded and bounds-checked by the
    server."""

    def list(self, dev_eui: str) -> Dict[str, Any]:
        """`{deviceType, transport, commands, sent}`: what the device takes
        and the last 50 sent."""
        return self._client.request('GET', path('/api/v1/devices', dev_eui, 'commands'))

    def send(self, dev_eui: str, command_id: str, params: Optional[Dict[str, Any]] = None, *,
             confirmed: Optional[bool] = None) -> Dict[str, Any]:
        return self._client.request(
            'POST', path('/api/v1/devices', dev_eui, 'commands', command_id),
            json=compact(params=params or {}, confirmed=confirmed))


class Registry(Resource):
    """Devices the org is owner of record for, waiting to be claimed (org
    admin). A claim code exists in clear only in the response that issues it."""

    def list(self, *, status: Optional[str] = None) -> List[Dict[str, Any]]:
        return self._client.request('GET', '/api/v1/device-registry',
                                    params={'status': status})['result']

    def import_devices(self, devices: Optional[List[Dict[str, Any]]] = None, *,
                       csv: Optional[str] = None, device_type: Optional[str] = None,
                       profile_id: Optional[str] = None,
                       valid_days: Optional[int] = None) -> List[Dict[str, Any]]:
        """Each row `{devEui, joinEui, appKey, claimCode?, serial?, name?}`, or
        a sheet as `csv`. Returns each entry with `claimCode` and its TR005
        label (`qr`, `qrSvg`). All or nothing."""
        return self._client.request('POST', '/api/v1/device-registry', json=compact(
            devices=devices, csv=csv, deviceType=device_type, profileId=profile_id,
            validDays=valid_days))['result']

    def new_code(self, entry_id: str) -> Dict[str, Any]:
        """A new code for an unclaimed entry; the old one stops claiming."""
        return self._client.request('POST', path('/api/v1/device-registry', entry_id, 'code'))

    def withdraw(self, entry_id: str, *, confirm: str) -> Dict[str, Any]:
        return self._client.request('DELETE', path('/api/v1/device-registry', entry_id),
                                    json={'confirm': confirm})


class Transfers(Resource):
    """Offering devices to another org, and accepting what is offered. Both
    sides repeat the offer's `confirm` value: the DevEUI or application name."""

    def list(self, *, direction: Optional[str] = None,
             status: Optional[str] = None) -> List[Dict[str, Any]]:
        return self._client.request('GET', '/api/v1/device-transfers',
                                    params={'direction': direction, 'status': status})['result']

    def get(self, transfer_id: str) -> Dict[str, Any]:
        return self._client.request('GET', path('/api/v1/device-transfers', transfer_id))

    def offer(self, to_org: str, *, confirm: str, dev_eui: Optional[str] = None,
              application: Optional[str] = None, expires_in_days: Optional[int] = None,
              note: Optional[str] = None) -> Dict[str, Any]:
        return self._client.request('POST', '/api/v1/device-transfers', json=compact(
            toOrg=to_org, confirm=confirm, devEui=dev_eui, application=application,
            expiresInDays=expires_in_days, note=note))

    def accept(self, transfer_id: str, *, confirm: str, application: Optional[str] = None,
               profiles: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """The devices move in with their keys and session. A 502 means the
        LNS refused part way and every device moved was put back."""
        return self._client.request('POST', path('/api/v1/device-transfers', transfer_id, 'accept'),
                                    json=compact(confirm=confirm, application=application,
                                                 profiles=profiles))

    def decline(self, transfer_id: str) -> Dict[str, Any]:
        return self._client.request('POST', path('/api/v1/device-transfers', transfer_id, 'decline'))

    def cancel(self, transfer_id: str) -> Dict[str, Any]:
        return self._client.request('POST', path('/api/v1/device-transfers', transfer_id, 'cancel'))
