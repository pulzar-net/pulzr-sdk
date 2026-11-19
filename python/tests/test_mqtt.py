"""pulzr.mqtt: the topics and payloads it publishes, and what it does with
what arrives. The topic shapes are the server's (shared/mqtt_topics.py); a
helper that drifted from them would publish downlinks nobody receives."""

from __future__ import annotations

import json
import unittest
from types import SimpleNamespace

from pulzr import mqtt
from support import client, ok

INFO = {'host': 'mqtt.test', 'port': 8883, 'tls': True, 'username': 'riverside'}
EUI = 'A84041000181C061'
KEY = 'pzk_ab12cd34_' + 'k' * 40


class FakeClient:
    def __init__(self, _version, client_id='', clean_session=True):
        self.client_id, self.clean_session = client_id, clean_session
        self.calls = []

    def username_pw_set(self, username, password):
        self.calls.append(('auth', username, password))

    def tls_set(self):
        self.calls.append(('tls',))

    def connect(self, host, port, keepalive=60):
        self.calls.append(('connect', host, port))

    def subscribe(self, topic, qos=0):
        self.calls.append(('subscribe', topic, qos))

    def publish(self, topic, payload, qos=0, retain=False):
        self.calls.append(('publish', topic, json.loads(payload), qos, retain))


FAKE_PAHO = SimpleNamespace(Client=FakeClient, CallbackAPIVersion=SimpleNamespace(VERSION2=2))


class Topics(unittest.TestCase):
    def test_shapes(self):
        self.assertEqual(mqtt.org_filter('riverside'), 'v1/riverside/#')
        self.assertEqual(mqtt.uplink_topic('riverside', EUI), 'v1/riverside/devices/a84041000181c061/up')
        self.assertEqual(mqtt.down_topic('riverside', EUI, 'command'),
                         'v1/riverside/devices/a84041000181c061/down/command')
        self.assertEqual(mqtt.ack_topic('riverside', EUI), 'v1/riverside/devices/a84041000181c061/down/ack')
        with self.assertRaises(ValueError):
            mqtt.down_topic('riverside', EUI, 'ack')

    def test_payloads(self):
        self.assertEqual(mqtt.push_payload(f_port=10, data='AQ==', correlation_id='1'),
                         {'fPort': 10, 'confirmed': False, 'data': 'AQ==', 'correlationId': '1'})
        with self.assertRaises(ValueError):
            mqtt.push_payload(f_port=10, data='AQ==', object={'a': 1})
        with self.assertRaises(ValueError):
            mqtt.push_payload(f_port=10)
        self.assertEqual(mqtt.command_payload('reboot'), {'command': 'reboot', 'params': {}})

    def test_classify(self):
        event = {'id': 'evt_1', 'type': 'uplink.received', 'data': {}}
        self.assertEqual(mqtt.classify('v1/r/devices/a84041000181c061/up', json.dumps(event).encode()),
                         ('event', event))
        self.assertEqual(mqtt.classify('v1/r/devices/a84041000181c061/down/ack', b'{"ok": true}'),
                         ('ack', {'ok': True}))
        self.assertEqual(mqtt.classify('v1/r/devices/a84041000181c061/down/push', b'{"fPort": 1}')[0],
                         'downlink')
        self.assertEqual(mqtt.classify('v1/r/x', b'not json')[0], 'unknown')


class Session(unittest.TestCase):
    def test_connects_with_the_key_as_password_and_publishes(self):
        session = mqtt.Session(KEY, client_id='app-1', info=INFO, mqtt_module=FAKE_PAHO)
        c = session.client
        self.assertFalse(c.clean_session)
        self.assertEqual(c.client_id, 'pzk_ab12cd34-app-1')
        self.assertEqual(c.calls[:3], [('auth', 'riverside', KEY), ('tls',),
                                       ('connect', 'mqtt.test', 8883)])
        session.subscribe()
        session.push(EUI, f_port=10, data='AQ==', correlation_id='c1')
        session.command(EUI, 'set_interval', {'minutes': 15})
        self.assertEqual(c.calls[3:], [
            ('subscribe', 'v1/riverside/#', 1),
            ('publish', 'v1/riverside/devices/a84041000181c061/down/push',
             {'fPort': 10, 'confirmed': False, 'data': 'AQ==', 'correlationId': 'c1'}, 1, False),
            ('publish', 'v1/riverside/devices/a84041000181c061/down/command',
             {'command': 'set_interval', 'params': {'minutes': 15}}, 1, False),
        ])

    def test_routes_events_and_acks(self):
        session = mqtt.Session(KEY, persistent=False, info={**INFO, 'tls': False},
                               mqtt_module=FAKE_PAHO)
        self.assertNotIn(('tls',), session.client.calls)
        seen = []
        session.on_event = lambda topic, event: seen.append(('event', event['id']))
        session.on_ack = lambda topic, ack: seen.append(('ack', ack['status']))
        for topic, body in [('v1/riverside/devices/a84041000181c061/up', {'id': 'evt_1', 'type': 'uplink.received'}),
                            ('v1/riverside/devices/a84041000181c061/down/ack', {'status': 201}),
                            ('v1/riverside/devices/a84041000181c061/down/push', {'fPort': 1})]:
            session._on_message(None, None, SimpleNamespace(topic=topic, payload=json.dumps(body).encode()))
        self.assertEqual(seen, [('event', 'evt_1'), ('ack', 201)])

    def test_resubscribes_on_reconnect(self):
        session = mqtt.Session(KEY, client_id='a', info=INFO, mqtt_module=FAKE_PAHO)
        session.subscribe('v1/riverside/devices/+/up')
        session.client.calls.clear()
        session._on_connect(session.client, None, None, 0)
        self.assertEqual(session.client.calls, [('subscribe', [('v1/riverside/devices/+/up', 1)], 0)])

    def test_client_ids_start_with_the_key_prefix(self):
        # The broker refuses any other: the id names a session, and the
        # prefix makes it this key's.
        self.assertEqual(mqtt.client_id_for(KEY, 'cold-chain-1'), 'pzk_ab12cd34-cold-chain-1')
        self.assertEqual(mqtt.client_id_for(KEY, 'pzk_ab12cd34-mine'), 'pzk_ab12cd34-mine')
        self.assertRegex(mqtt.client_id_for(KEY), r'^pzk_ab12cd34-[0-9a-f]{12}$')
        self.assertNotEqual(mqtt.client_id_for(KEY), mqtt.client_id_for(KEY))
        with self.assertRaises(ValueError):
            mqtt.client_id_for('not-a-key', 'x')
        session = mqtt.Session(KEY, persistent=False, info=INFO, mqtt_module=FAKE_PAHO)
        self.assertTrue(session.client.client_id.startswith('pzk_ab12cd34-'))

    def test_persistent_needs_a_client_id(self):
        with self.assertRaises(ValueError):
            mqtt.Session(KEY, info=INFO, mqtt_module=FAKE_PAHO)


class Connection(unittest.TestCase):
    def test_reads_the_connection(self):
        c, script, _ = client([ok({**INFO, 'topics': {'all': 'v1/riverside/#'}})])
        self.assertEqual(c.mqtt.connection()['username'], 'riverside')
        self.assertEqual(script.requests[0].url.path, '/api/v1/mqtt/connection')


if __name__ == '__main__':
    unittest.main()
