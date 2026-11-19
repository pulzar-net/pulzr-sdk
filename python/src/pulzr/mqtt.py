"""The org's events over MQTT, and downlinks sent by publishing.

    pip install "pulzr[mqtt]"

    from pulzr import mqtt

    session = mqtt.Session(client_id='cold-chain-1')     # PULZR_API_KEY
    # connects as pzk_<key prefix>-cold-chain-1
    session.on_event = lambda topic, event: print(event['type'], event['subject'])
    session.on_ack = lambda topic, ack: print(ack['status'], ack['correlationId'])
    session.subscribe()                                   # v1/<org>/#
    session.push('a84041000181c061', f_port=10, data='AQ==', correlation_id='r-1')
    session.loop_forever()

The broker, the username and the topics come from
`GET /api/v1/mqtt/connection`, asked once with the same key, so nothing here
hard-codes a host. paho-mqtt is imported only when a `Session` is made: the
topic and payload helpers below work without it.

The topics, the envelope and the ack are in /docs/mqtt.
"""

from __future__ import annotations

import json
import os
import re
import secrets
from typing import Any, Callable, Dict, Optional, Tuple

from ._client import env

PREFIX = 'v1'
DOWN_KINDS = ('push', 'command')


def client_id_for(api_key: str, name: Optional[str] = None) -> str:
    """A client id the broker accepts for this key: the key's prefix (`pzk_`
    and 8 hex, its first 12 characters), a dash, then `name` -- or a random
    suffix for a session that need not outlast the process.

    The broker refuses any other: a client id names a session the next
    connection under it resumes, and the prefix makes it this key's alone.
    A `name` that already starts with the prefix is used as it is.
    """
    prefix = api_key[:12]
    if not re.fullmatch(r'pzk_[0-9a-f]{8}', prefix):
        raise ValueError('Not a Pulzar API key: expected pzk_<8 hex>_...')
    if name and name.startswith(prefix):
        return name
    return f'{prefix}-{name or secrets.token_hex(6)}'


def org_filter(org: str) -> str:
    return f'{PREFIX}/{org}/#'


def uplink_topic(org: str, dev_eui: str) -> str:
    return f'{PREFIX}/{org}/devices/{dev_eui.lower()}/up'


def down_topic(org: str, dev_eui: str, kind: str) -> str:
    if kind not in DOWN_KINDS:
        raise ValueError(f'kind must be one of {DOWN_KINDS}')
    return f'{PREFIX}/{org}/devices/{dev_eui.lower()}/down/{kind}'


def ack_topic(org: str, dev_eui: str) -> str:
    return f'{PREFIX}/{org}/devices/{dev_eui.lower()}/down/ack'


def push_payload(*, f_port: int, data: Optional[str] = None,
                 object: Optional[Dict[str, Any]] = None, confirmed: bool = False,
                 correlation_id: Optional[str] = None) -> Dict[str, Any]:
    """The JSON for `down/push`: `data` (base64) or `object`, not both."""
    if (data is None) == (object is None):
        raise ValueError('Give data or object, not both')
    body: Dict[str, Any] = {'fPort': f_port, 'confirmed': confirmed}
    if data is not None:
        body['data'] = data
    else:
        body['object'] = object
    if correlation_id is not None:
        body['correlationId'] = correlation_id
    return body


def command_payload(command: str, params: Optional[Dict[str, Any]] = None, *,
                    confirmed: Optional[bool] = None,
                    correlation_id: Optional[str] = None) -> Dict[str, Any]:
    body: Dict[str, Any] = {'command': command, 'params': params or {}}
    if confirmed is not None:
        body['confirmed'] = confirmed
    if correlation_id is not None:
        body['correlationId'] = correlation_id
    return body


def classify(topic: str, payload: bytes) -> Tuple[str, Any]:
    """('event', envelope), ('ack', ack), ('downlink', body) for another
    client's push or command, or ('unknown', raw) for anything else."""
    try:
        body = json.loads(payload)
    except (ValueError, TypeError):
        return 'unknown', payload
    parts = topic.split('/')
    if len(parts) == 6 and parts[0] == PREFIX and parts[2] == 'devices' and parts[4] == 'down':
        return ('ack' if parts[5] == 'ack' else 'downlink'), body
    if parts[0] == PREFIX and isinstance(body, dict) and 'id' in body and 'type' in body:
        return 'event', body
    return 'unknown', body


Handler = Callable[[str, Dict[str, Any]], None]


class Session:
    """One MQTT connection for one API key.

    `persistent` keeps the broker session across reconnects (clean session
    off), so events published while the process was down are delivered when
    it comes back. It needs a `client_id` that stays the same between runs.
    The id sent is `client_id_for(api_key, client_id)`: the key's prefix first.
    """

    def __init__(self, api_key: Optional[str] = None, *, client_id: Optional[str] = None,
                 persistent: bool = True, info: Optional[Dict[str, Any]] = None,
                 base_url: Optional[str] = None, mqtt_module: Any = None) -> None:
        api_key = api_key or env('PULZR_API_KEY')
        if not api_key:
            raise ValueError('An API key is required: pass api_key or set PULZR_API_KEY')
        if persistent and not client_id:
            raise ValueError('A persistent session needs a client_id that is the same every run')
        if info is None:
            from ._client import DEFAULT_BASE_URL, Client

            with Client(api_key, base_url=base_url or DEFAULT_BASE_URL) as client:
                info = client.mqtt.connection()
        self.info = info
        self.org: str = info['username']
        self.on_event: Optional[Handler] = None
        self.on_ack: Optional[Handler] = None

        if mqtt_module is None:
            try:
                import paho.mqtt.client as mqtt_module
            except ImportError as e:
                raise ImportError('MQTT needs paho-mqtt: pip install "pulzr[mqtt]"') from e
        self._mqtt = mqtt_module
        self.client_id = client_id_for(api_key, client_id)
        self.client = mqtt_module.Client(mqtt_module.CallbackAPIVersion.VERSION2,
                                         client_id=self.client_id, clean_session=not persistent)
        self.client.username_pw_set(self.org, api_key)
        if info.get('tls', True):
            self.client.tls_set()
        self.client.on_message = self._on_message
        self._filters: Dict[str, int] = {}
        self.client.on_connect = self._on_connect
        self.client.connect(info['host'], int(info['port']), keepalive=60)

    def _on_connect(self, client: Any, _userdata: Any, _flags: Any, reason_code: Any,
                    _properties: Any = None) -> None:
        # Again on every reconnect: a clean session forgets its subscriptions.
        if self._filters:
            client.subscribe(list(self._filters.items()))

    def _on_message(self, _client: Any, _userdata: Any, message: Any) -> None:
        kind, body = classify(message.topic, message.payload)
        if kind == 'event' and self.on_event:
            self.on_event(message.topic, body)
        elif kind == 'ack' and self.on_ack:
            self.on_ack(message.topic, body)

    def subscribe(self, topic_filter: Optional[str] = None) -> None:
        """Everything in the org by default. QoS 1, which is what the network
        publishes at; deduplicate on each event's `id`."""
        topic_filter = topic_filter or org_filter(self.org)
        self._filters[topic_filter] = 1
        self.client.subscribe(topic_filter, qos=1)

    def push(self, dev_eui: str, *, f_port: int, data: Optional[str] = None,
             object: Optional[Dict[str, Any]] = None, confirmed: bool = False,
             correlation_id: Optional[str] = None) -> Any:
        """Publish a downlink. Its result arrives on `on_ack`; subscribe first
        to receive it."""
        body = push_payload(f_port=f_port, data=data, object=object, confirmed=confirmed,
                            correlation_id=correlation_id)
        return self.client.publish(down_topic(self.org, dev_eui, 'push'), json.dumps(body),
                                   qos=1, retain=False)

    def command(self, dev_eui: str, command: str, params: Optional[Dict[str, Any]] = None, *,
                confirmed: Optional[bool] = None, correlation_id: Optional[str] = None) -> Any:
        body = command_payload(command, params, confirmed=confirmed, correlation_id=correlation_id)
        return self.client.publish(down_topic(self.org, dev_eui, 'command'), json.dumps(body),
                                   qos=1, retain=False)

    def loop_forever(self) -> None:
        self.client.loop_forever()

    def loop_start(self) -> None:
        self.client.loop_start()

    def disconnect(self) -> None:
        self.client.disconnect()
