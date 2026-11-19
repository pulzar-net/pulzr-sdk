import assert from 'node:assert/strict';
import { test } from 'node:test';

import { PulzrClient } from '../src/index.js';
import { KEY, json, mockFetch } from './helpers.js';

const EUI = 'a84041000181c061';
const SESSION = '3f1c2b4a-5d6e-4f70-8a9b-0c1d2e3f4a5b';

test('airtime, location and coverage reach the routes net-api serves', async () => {
  const fetch = mockFetch(() => json({ result: [], features: [] }));
  const client = new PulzrClient({ apiKey: KEY, fetch });
  await client.airtime.device(EUI, { days: 3 });
  await client.airtime.day({ day: '2026-10-13' });
  await client.devices.location(EUI, { history: 5 });
  await client.coverage.cells({ gatewayId: 'aa555a0000000001', resolution: 8, bbox: [-118.3, 34, -118.2, 34.1] });
  await client.coverage.at(34.02, -118.28);
  await client.coverage.public([-118.3, 34, -118.2, 34.1]);
  await client.coverage.setPublic(true);
  await client.coverage.startSession(EUI);
  await client.coverage.addFixes(SESSION, [{ time: 1760356800000, latitude: 34.02, longitude: -118.28, accuracy: 6 }]);
  await client.coverage.stopSession(SESSION);

  assert.deepEqual(fetch.calls.map((c) => `${c.method} ${c.url.pathname}`), [
    `GET /api/v1/devices/${EUI}/airtime`,
    'GET /api/v1/airtime',
    `GET /api/v1/devices/${EUI}/location`,
    'GET /api/v1/coverage',
    'GET /api/v1/coverage/at',
    'GET /api/v1/public/coverage',
    'PUT /api/v1/coverage/settings',
    'POST /api/v1/coverage/sessions',
    `POST /api/v1/coverage/sessions/${SESSION}/fixes`,
    `POST /api/v1/coverage/sessions/${SESSION}/stop`,
  ]);
  assert.equal(fetch.calls[0]!.url.searchParams.get('days'), '3');
  assert.equal(fetch.calls[3]!.url.searchParams.get('bbox'), '-118.3,34,-118.2,34.1');
  assert.equal(fetch.calls[3]!.url.searchParams.get('gatewayId'), 'aa555a0000000001');
  assert.equal(fetch.calls[4]!.url.searchParams.get('latitude'), '34.02');
  assert.deepEqual(fetch.calls[6]!.body, { public: true });
  assert.deepEqual(fetch.calls[7]!.body, { devEui: EUI });
  assert.deepEqual(fetch.calls[8]!.body, {
    fixes: [{ time: 1760356800000, latitude: 34.02, longitude: -118.28, accuracy: 6 }],
  });
});
