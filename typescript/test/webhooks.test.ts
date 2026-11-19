import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

import { WebhookSignatureError, constructEvent, verifyWebhook } from '../src/index.js';

interface Case {
  name: string;
  note: string;
  secret: string;
  body: string;
  bodyBase64: string;
  header: string;
  now: number;
  tolerance: number;
  valid: boolean;
}

// dist-test/test/ -> sdk/fixtures/
const fixtures = JSON.parse(
  readFileSync(new URL('../../../fixtures/webhook-signatures.json', import.meta.url), 'utf8'),
) as { header: string; cases: Case[] };

const bytes = (c: Case) => new Uint8Array(Buffer.from(c.bodyBase64, 'base64'));

test('the fixtures name the header the SDK sends', () => {
  assert.equal(fixtures.header, 'Parkeze-Signature');
  assert.ok(fixtures.cases.length >= 14);
});

for (const c of fixtures.cases) {
  test(`fixture ${c.name}: ${c.note}`, async () => {
    const opts = { now: c.now, tolerance: c.tolerance };
    assert.equal(await verifyWebhook(c.secret, bytes(c), c.header, opts), c.valid, 'Uint8Array');
    // The same bytes, as an ArrayBuffer and as the decoded string.
    const view = bytes(c);
    const buffer = view.buffer.slice(view.byteOffset, view.byteOffset + view.byteLength) as ArrayBuffer;
    assert.equal(await verifyWebhook(c.secret, buffer, c.header, opts), c.valid, 'ArrayBuffer');
    assert.equal(await verifyWebhook(c.secret, c.body, c.header, opts), c.valid, 'string');
    // A list holding the secret and a stranger verifies exactly as the secret alone.
    assert.equal(await verifyWebhook(['whsec_' + '00'.repeat(24), c.secret], bytes(c), c.header, opts), c.valid, 'list');
  });
}

const valid = fixtures.cases.find((c) => c.name === 'valid')!;
const expired = fixtures.cases.find((c) => c.name === 'expired')!;

test('an empty secret list verifies nothing', async () => {
  assert.equal(await verifyWebhook([], bytes(valid), valid.header, { now: valid.now }), false);
});

test('the default tolerance is 300 s', async () => {
  assert.equal(await verifyWebhook(expired.secret, bytes(expired), expired.header, { now: expired.now }), false);
  assert.equal(await verifyWebhook(expired.secret, bytes(expired), expired.header, { now: expired.now - 1 }), true);
});

test('a wider tolerance accepts an older delivery', async () => {
  assert.equal(
    await verifyWebhook(expired.secret, bytes(expired), expired.header, { now: expired.now, tolerance: 400 }),
    true,
  );
});

test('constructEvent returns the typed envelope', async () => {
  const event = await constructEvent(valid.secret, bytes(valid), valid.header, { now: valid.now });
  assert.equal(event.id, 'evt_01K7ZQ8V3N4M2X9B6C5D7E8F0G');
  assert.equal(event.type, 'uplink.received');
  if (event.type === 'uplink.received') assert.equal(event.data.device.name, 'Lot B 14');
});

test('constructEvent throws WebhookSignatureError on a bad or missing signature', async () => {
  await assert.rejects(constructEvent(valid.secret, bytes(valid), expired.header, { now: valid.now + 1000 }),
    WebhookSignatureError);
  await assert.rejects(constructEvent(valid.secret, bytes(valid), undefined), WebhookSignatureError);
  await assert.rejects(constructEvent('whsec_other', valid.body, valid.header, { now: valid.now }),
    WebhookSignatureError);
});

test('verifies without a global crypto, as on Node 18', async () => {
  const descriptor = Object.getOwnPropertyDescriptor(globalThis, 'crypto');
  Object.defineProperty(globalThis, 'crypto', { value: undefined, configurable: true, writable: true });
  try {
    assert.equal((globalThis as { crypto?: unknown }).crypto, undefined);
    assert.equal(await verifyWebhook(valid.secret, bytes(valid), valid.header, { now: valid.now }), true);
    assert.equal(await verifyWebhook(valid.secret, bytes(valid), expired.header, { now: valid.now + 1000 }), false);
  } finally {
    if (descriptor) Object.defineProperty(globalThis, 'crypto', descriptor);
    else delete (globalThis as { crypto?: unknown }).crypto;
  }
  // Put back as it was: present on Node 19+, absent on Node 18, where there
  // was nothing to restore and asserting one existed failed every run.
  assert.equal(Object.getOwnPropertyDescriptor(globalThis, 'crypto')?.value,
               descriptor?.value);
});
