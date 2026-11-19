import assert from 'node:assert/strict';
import { test } from 'node:test';

import { PulzrClient } from '../src/index.js';
import { KEY, json, mockFetch } from './helpers.js';

const GW = 'b827ebfffe6151c7';

test('Basics Station wrappers reach the routes net-api serves', async () => {
  const fetch = mockFetch(() => json({ state: 'active', files: {} }));
  const client = new PulzrClient({ apiKey: KEY, fetch });
  await client.basicStation.register(GW, 'Roof 1');
  await client.basicStation.status(GW);
  await client.basicStation.setup(GW, { auth: 'certificate' });
  await client.basicStation.rotate(GW);
  await client.basicStation.revoke(GW, GW);

  assert.deepEqual(fetch.calls.map((c) => `${c.method} ${c.url.pathname}`), [
    'POST /api/v1/gateways/basic-station',
    `GET /api/v1/gateways/${GW}/basic-station`,
    `POST /api/v1/gateways/${GW}/basic-station/setup`,
    `POST /api/v1/gateways/${GW}/basic-station/rotate`,
    `POST /api/v1/gateways/${GW}/basic-station/revoke`,
  ]);
  assert.deepEqual(fetch.calls[0]!.body, { gatewayId: GW, name: 'Roof 1', auth: 'token' });
  assert.deepEqual(fetch.calls[2]!.body, { auth: 'certificate' });
  assert.deepEqual(fetch.calls[4]!.body, { confirm: GW });
});
