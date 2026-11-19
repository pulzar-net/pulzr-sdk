import assert from 'node:assert/strict';
import { test } from 'node:test';

import { PulzrClient } from '../src/index.js';
import { KEY, json, mockFetch } from './helpers.js';

const GW = 'ac1f09fffe0b1c2d';
const OFFER = '9d3c1a7e-5f2b-4c8d-a1e0-7b6f5d4c3b2a';

test('gateway wrappers reach the routes net-api serves', async () => {
  const fetch = mockFetch(() => json({ result: [{ gatewayId: GW, can: ['read'] }] }));
  const client = new PulzrClient({ apiKey: KEY, fetch });
  const gateways = await client.gateways.list();
  assert.deepEqual(gateways[0]!.can, ['read']);
  await client.gateways.metrics(GW, { hours: 48 });
  await client.gateways.devices(GW, { days: 3 });
  await client.gateways.status(GW);
  await client.gateways.backhaul(GW);
  await client.gateways.restart(GW);
  await client.gateways.offer(GW, { toOrg: 'columbia', confirm: GW });
  await client.gateways.transfers();
  await client.gateways.accept(OFFER, GW);
  await client.gateways.decline(OFFER);
  await client.gateways.cancel(OFFER);

  assert.deepEqual(fetch.calls.map((c) => `${c.method} ${c.url.pathname}`), [
    'GET /api/v1/gateways',
    `GET /api/v1/gateways/${GW}/metrics`,
    `GET /api/v1/gateways/${GW}/devices`,
    `GET /api/v1/gateway-ops/${GW}/status`,
    `GET /api/v1/gateway-ops/${GW}/backhaul`,
    `POST /api/v1/gateway-ops/${GW}/restart`,
    `POST /api/v1/gateway-ops/gateways/${GW}/transfer`,
    'GET /api/v1/gateway-ops/transfers',
    `POST /api/v1/gateway-ops/transfers/${OFFER}/accept`,
    `POST /api/v1/gateway-ops/transfers/${OFFER}/decline`,
    `POST /api/v1/gateway-ops/transfers/${OFFER}/cancel`,
  ]);
  assert.equal(fetch.calls[1]!.url.searchParams.get('hours'), '48');
  assert.equal(fetch.calls[2]!.url.searchParams.get('days'), '3');
  assert.deepEqual(fetch.calls[6]!.body, { toOrg: 'columbia', confirm: GW });
  assert.deepEqual(fetch.calls[8]!.body, { confirm: GW });
});
