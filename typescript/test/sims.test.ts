import assert from 'node:assert/strict';
import { test } from 'node:test';

import { PulzrClient } from '../src/index.js';
import { KEY, json, mockFetch } from './helpers.js';

const ICCID = '8988228066614207616';

test('SIM wrappers reach the routes net-api serves', async () => {
  const fetch = mockFetch(() => json({ result: [{ iccid: ICCID, can: ['read'] }], orphaned: [] }));
  const client = new PulzrClient({ apiKey: KEY, fetch });
  const sims = await client.sims.list();
  assert.deepEqual(sims.result[0]!.can, ['read']);
  await client.sims.status();
  await client.sims.usage({ days: 30 });
  await client.sims.get(ICCID);
  await client.sims.billing(ICCID);
  await client.sims.update(ICCID, { enabled: false, imeiLock: false });
  await client.sims.reset(ICCID);

  assert.deepEqual(fetch.calls.map((c) => `${c.method} ${c.url.pathname}`), [
    'GET /api/v1/sims',
    'GET /api/v1/sims/status',
    'GET /api/v1/sims/usage',
    `GET /api/v1/sims/${ICCID}/detail`,
    `GET /api/v1/sims/${ICCID}/billing`,
    `PATCH /api/v1/sims/${ICCID}`,
    `POST /api/v1/sims/${ICCID}/reset`,
  ]);
  assert.equal(fetch.calls[2]!.url.searchParams.get('days'), '30');
  // False is a deliberate disable and a deliberate unlock, so it is sent.
  assert.deepEqual(fetch.calls[5]!.body, { enabled: false, imeiLock: false });
});
