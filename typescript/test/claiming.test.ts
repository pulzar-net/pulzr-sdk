import assert from 'node:assert/strict';
import { test } from 'node:test';

import { EVENT_TYPES, PulzrClient } from '../src/index.js';
import { KEY, json, mockFetch } from './helpers.js';

const EUI = 'a84041000181c061';
const TID = '9d3c1a7e-5f2b-4c8d-a1e0-7b6f5d4c3b2a';

test('claiming, the registry and transfers reach the routes net-api serves', async () => {
  const fetch = mockFetch(() => json({ result: [] }));
  const client = new PulzrClient({ apiKey: KEY, fetch });
  await client.devices.claim({ qr: 'LW:D0:0000000000000000:A84041000181C061:00000000:OABCDEF12' });
  await client.devices.release(EUI, { confirm: EUI });
  await client.devices.registry.list({ status: 'unclaimed' });
  await client.devices.registry.import({ csv: 'DevEUI,AppKey', profileId: 'A1B2C3D4' });
  await client.devices.transfers.list({ direction: 'incoming', status: 'open' });
  await client.devices.transfers.offer({ toOrg: 'facilities', application: 'Lot B', confirm: 'Lot B' });
  await client.devices.transfers.accept(TID, { confirm: 'Lot B' });
  await client.devices.transfers.decline(TID);
  assert.deepEqual(fetch.calls.map((c) => `${c.method} ${c.url.pathname}`), [
    'POST /api/v1/devices/claim',
    `POST /api/v1/devices/${EUI}/release`,
    'GET /api/v1/device-registry',
    'POST /api/v1/device-registry',
    'GET /api/v1/device-transfers',
    'POST /api/v1/device-transfers',
    `POST /api/v1/device-transfers/${TID}/accept`,
    `POST /api/v1/device-transfers/${TID}/decline`,
  ]);
  assert.deepEqual(fetch.calls[5]!.body, { toOrg: 'facilities', application: 'Lot B', confirm: 'Lot B' });
  assert.equal(fetch.calls[4]!.url.searchParams.get('status'), 'open');
});

test('the transfer and claim events are known types', () => {
  for (const type of ['device.claimed', 'device.transferred_out', 'device.transferred_in']) {
    assert.ok((EVENT_TYPES as readonly string[]).includes(type), type);
  }
});
