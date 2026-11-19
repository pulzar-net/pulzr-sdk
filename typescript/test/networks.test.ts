import assert from 'node:assert/strict';
import { test } from 'node:test';

import { PulzrClient } from '../src/index.js';
import { KEY, json, mockFetch } from './helpers.js';

const GW = 'ac1f09fffe0b1c2d';

test('gateways.network reaches the route net-api serves', async () => {
  const fetch = mockFetch(() =>
    json({ gatewayId: GW, wireguard: null, sshCa: false,
           cellular: { kind: 'cellular', slug: 'acme', name: 'Acme', owner: 'organization' } }));
  const client = new PulzrClient({ apiKey: KEY, fetch });
  const network = await client.gateways.network(GW);
  assert.equal(network.cellular?.owner, 'organization');
  assert.deepEqual(fetch.calls.map((c) => `${c.method} ${c.url.pathname}`), [
    `GET /api/v1/gateways/${GW}/network`,
  ]);
});
