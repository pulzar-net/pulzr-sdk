import assert from 'node:assert/strict';
import { test } from 'node:test';

import { PulzrClient } from '../src/index.js';
import { KEY, collect, json, mockFetch, sse } from './helpers.js';

const frame = (event: string, data: unknown) => `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;

test('registerDevices dry run sends dryRun and returns parsed rows', async () => {
  const fetch = mockFetch(() => json({ rows: [{ name: null, devEui: 'a840410000000001', problem: null }], problems: [] }));
  const client = new PulzrClient({ apiKey: KEY, fetch });
  const parsed = await client.onboarding.registerDevices('s1', { qr: ['LW:D0:0000000000000000:A840410000000001:00000000'], dryRun: true });
  assert.equal(parsed.rows.length, 1);
  assert.equal(fetch.calls[0]!.url.pathname, '/api/v1/onboarding/sessions/s1/devices');
  assert.deepEqual(fetch.calls[0]!.body, { qr: ['LW:D0:0000000000000000:A840410000000001:00000000'], dryRun: true });
});

test('start sends a PDF as base64', async () => {
  const fetch = mockFetch(() => json({ id: 's1', status: 'identifying' }, 202));
  const client = new PulzrClient({ apiKey: KEY, fetch });
  await client.onboarding.start({ datasheetPdf: new Uint8Array([0x25, 0x50, 0x44, 0x46]), vendor: 'Acme' });
  assert.deepEqual(fetch.calls[0]!.body, { datasheetPdf: 'JVBERg==', vendor: 'Acme' });
});

test('watch yields typed events and stops at end', async () => {
  const fetch = mockFetch(() => sse([
    ': open\n\n',
    frame('session', { id: 's1', status: 'waiting_for_uplink' }),
    ': tick\n\n',
    frame('join', { devEui: 'a840410000000001', time: '2026-10-13T14:00:00+00:00' }),
    frame('uplink', { devEui: 'a840410000000001', time: '2026-10-13T14:00:05+00:00', fPort: 1, fCnt: 0,
      rssi: -80, snr: 7.5, data: { temp: 21.4 },
      readings: [{ quantity: 'temperature', channel: null, value: 21.4, unit: '°C', field: 'temp' }] }),
    frame('end', { reason: 'abandoned' }),
    frame('session', { id: 's1', status: 'abandoned' }),
  ]));
  const client = new PulzrClient({ apiKey: KEY, fetch });
  const events = await collect(client.onboarding.watch('s1'));
  assert.deepEqual(events.map((e) => e.type), ['session', 'join', 'uplink', 'end']);
  const uplink = events[2]!;
  assert.ok(uplink.type === 'uplink');
  assert.equal(uplink.data.readings[0]?.value, 21.4);
});
