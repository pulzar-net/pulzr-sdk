import assert from 'node:assert/strict';
import { test } from 'node:test';

import { PulzrClient } from '../src/index.js';
import { KEY, json, mockFetch } from './helpers.js';

const ID = '6f1d2c3b-4a5e-4f60-9b7a-8c9d0e1f2a3b';

test('integrations reach their routes with the bodies the routes read', async () => {
  const fetch = mockFetch((call) => {
    if (call.method === 'DELETE') return new Response(null, { status: 204 });
    if (call.url.pathname.endsWith('/templates') || call.method === 'GET') return json({ result: [] });
    return json({ id: ID }, call.url.pathname.endsWith('/test') ? 202 : 201);
  });
  const client = new PulzrClient({ apiKey: KEY, fetch });
  await client.integrations.templates();
  await client.integrations.create({
    template: 'influxdb',
    name: 'Fleet history',
    settings: { url: 'https://influx.example.com', bucket: 'sensors', token: 't' },
  });
  await client.integrations.update(ID, { settings: { bucket: 'fleet' }, enabled: false });
  await client.integrations.test(ID, { devEui: 'a84041000181c061' });
  await client.integrations.deliveries(ID, { status: 'failed', limit: 5 });
  await client.integrations.retryDelivery('d1');
  await client.integrations.delete(ID);
  assert.deepEqual(
    fetch.calls.map((c) => [c.method, c.url.pathname]),
    [
      ['GET', '/api/v1/integrations/templates'],
      ['POST', '/api/v1/integrations'],
      ['PATCH', `/api/v1/integrations/${ID}`],
      ['POST', `/api/v1/integrations/${ID}/test`],
      ['GET', `/api/v1/integrations/${ID}/deliveries`],
      ['POST', '/api/v1/integrations/deliveries/d1/retry'],
      ['DELETE', `/api/v1/integrations/${ID}`],
    ],
  );
  assert.deepEqual(fetch.calls[1]!.body, {
    template: 'influxdb',
    name: 'Fleet history',
    settings: { url: 'https://influx.example.com', bucket: 'sensors', token: 't' },
  });
  assert.deepEqual(fetch.calls[2]!.body, { settings: { bucket: 'fleet' }, enabled: false });
  assert.deepEqual(fetch.calls[3]!.body, { devEui: 'a84041000181c061' });
  assert.equal(fetch.calls[4]!.url.searchParams.get('status'), 'failed');
});
