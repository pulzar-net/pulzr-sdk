import assert from 'node:assert/strict';
import { test } from 'node:test';

import { PulzrClient } from '../src/index.js';
import { KEY, json, mockFetch } from './helpers.js';

const GROUP = 'aaaaaaaa-0000-4000-8000-000000000001';
const DEP = '9c8b7a6d-5e4f-4a3b-9c2d-1e0f9a8b7c6d';
const IMAGE = '5b9e7c1a-2d3f-4e5a-8b6c-7d8e9f0a1b2c';
const RELAY = '0016c001ff100001';
const EUI = '0016c001ff100002';

test('multicast groups and relays reach their routes with the bodies the routes read', async () => {
  const fetch = mockFetch((call) =>
    call.method === 'GET' ? json({ result: [] }) : json({ id: GROUP, fCnt: 1 }, call.method === 'POST' ? 201 : 200));
  const client = new PulzrClient({ apiKey: KEY, fetch });
  await client.multicastGroups.list();
  await client.multicastGroups.create({ name: 'Lot 4', applicationId: 'app-1', region: 'EU868' });
  await client.multicastGroups.addDevice(GROUP, EUI);
  await client.multicastGroups.send(GROUP, 10, 'AQI=');
  await client.relays.list();
  await client.relays.addDevice(RELAY, EUI);
  assert.deepEqual(
    fetch.calls.map((c) => [c.method, c.url.pathname]),
    [
      ['GET', '/api/v1/multicast-groups'],
      ['POST', '/api/v1/multicast-groups'],
      ['POST', `/api/v1/multicast-groups/${GROUP}/devices`],
      ['POST', `/api/v1/multicast-groups/${GROUP}/queue`],
      ['GET', '/api/v1/relays'],
      ['POST', `/api/v1/relays/${RELAY}/devices`],
    ],
  );
  assert.deepEqual(fetch.calls[1]!.body, { name: 'Lot 4', applicationId: 'app-1', region: 'EU868' });
  assert.deepEqual(fetch.calls[2]!.body, { devEui: EUI });
  assert.deepEqual(fetch.calls[3]!.body, { fPort: 10, data: 'AQI=' });
  assert.deepEqual(fetch.calls[5]!.body, { devEui: EUI });
});

test('a firmware deployment is planned, created and started with its name typed', async () => {
  const fetch = mockFetch((call) =>
    call.method === 'GET' ? json({ id: DEP, status: 'running', devices: [] }) : json({ id: DEP, status: 'draft' }, 201));
  const client = new PulzrClient({ apiKey: KEY, fetch });
  await client.firmware.plan({ imageId: IMAGE, tags: { lot: '4' } });
  await client.firmware.create('Lot 4 to 2.1', { imageId: IMAGE, devEuis: [EUI], redundancyPercent: 20 });
  await client.firmware.start(DEP, 'Lot 4 to 2.1');
  await client.firmware.get(DEP);
  await client.firmware.cancel(DEP);
  assert.deepEqual(
    fetch.calls.map((c) => [c.method, c.url.pathname]),
    [
      ['POST', '/api/v1/firmware/plan'],
      ['POST', '/api/v1/firmware/deployments'],
      ['POST', `/api/v1/firmware/deployments/${DEP}/start`],
      ['GET', `/api/v1/firmware/deployments/${DEP}`],
      ['POST', `/api/v1/firmware/deployments/${DEP}/cancel`],
    ],
  );
  assert.deepEqual(fetch.calls[0]!.body, { imageId: IMAGE, tags: { lot: '4' } });
  assert.deepEqual(fetch.calls[1]!.body, {
    name: 'Lot 4 to 2.1', imageId: IMAGE, devEuis: [EUI], redundancyPercent: 20,
  });
  assert.deepEqual(fetch.calls[2]!.body, { confirm: 'Lot 4 to 2.1' });
});
