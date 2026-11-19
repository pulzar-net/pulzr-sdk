import assert from 'node:assert/strict';
import { test } from 'node:test';

import { PulzrClient, mqttClientId, mqttTopics } from '../src/index.js';
import { KEY, json, mockFetch } from './helpers.js';

test('connection reads the org\'s broker settings', async () => {
  const fetch = mockFetch(() => json({ host: 'mqtt.test', port: 8883, tls: true, username: 'riverside' }));
  const client = new PulzrClient({ apiKey: KEY, fetch });
  const info = await client.mqtt.connection();
  assert.equal(info.username, 'riverside');
  assert.equal(fetch.calls[0]!.url.pathname, '/api/v1/mqtt/connection');
});

test('topics are the server\'s shapes', () => {
  const eui = 'A84041000181C061';
  assert.equal(mqttTopics.all('riverside'), 'v1/riverside/#');
  assert.equal(mqttTopics.uplink('riverside', eui), 'v1/riverside/devices/a84041000181c061/up');
  assert.equal(mqttTopics.deviceEvent('riverside', eui, 'device.offline'),
    'v1/riverside/devices/a84041000181c061/events/device.offline');
  assert.equal(mqttTopics.push('riverside', eui), 'v1/riverside/devices/a84041000181c061/down/push');
  assert.equal(mqttTopics.command('riverside', eui), 'v1/riverside/devices/a84041000181c061/down/command');
  assert.equal(mqttTopics.ack('riverside', eui), 'v1/riverside/devices/a84041000181c061/down/ack');
});

test('client ids start with the key prefix, which the broker requires', () => {
  const key = 'pzk_ab12cd34_' + 'k'.repeat(40);
  assert.equal(mqttClientId(key, 'cold-chain-1'), 'pzk_ab12cd34-cold-chain-1');
  assert.equal(mqttClientId(key, 'pzk_ab12cd34-mine'), 'pzk_ab12cd34-mine');
  assert.match(mqttClientId(key), /^pzk_ab12cd34-[0-9a-f]{12}$/);
  assert.notEqual(mqttClientId(key), mqttClientId(key));
  assert.throws(() => mqttClientId('not-a-key', 'x'));
});
