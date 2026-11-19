import assert from 'node:assert/strict';
import { test } from 'node:test';

import {
  AuthenticationError,
  ConflictError,
  ConnectionError,
  NotFoundError,
  PulzrClient,
  PulzrError,
  PermissionDeniedError,
  RateLimitError,
  ServerError,
  ValidationError,
} from '../src/index.js';
import { backoff } from '../src/core.js';
import { KEY, json, mockFetch } from './helpers.js';

test('sends the key, the org, JSON, and comma-joined lists', async () => {
  const fetch = mockFetch(() => json({ result: [] }));
  const client = new PulzrClient({ apiKey: KEY, org: 'usc', baseUrl: 'https://example.test/', fetch });
  await client.readings.latest({ quantity: 'temperature', devices: ['a840410000000001', 'a840410000000002'] });

  const call = fetch.calls[0]!;
  assert.equal(call.method, 'GET');
  assert.equal(call.url.origin + call.url.pathname, 'https://example.test/api/v1/readings/latest');
  assert.equal(call.url.searchParams.get('quantity'), 'temperature');
  assert.equal(call.url.searchParams.get('devices'), 'a840410000000001,a840410000000002');
  assert.equal(call.url.searchParams.has('channel'), false);
  assert.equal(call.headers.get('authorization'), `Bearer ${KEY}`);
  assert.equal(call.headers.get('x-active-org'), 'usc');
  assert.equal(call.headers.get('accept'), 'application/json');
  assert.equal(call.headers.get('content-type'), null);
});

test('no X-Active-Org without an org; a body is JSON with its content type', async () => {
  const fetch = mockFetch(() => json({ id: 'w1', secret: 'whsec_x' }, 201));
  const client = new PulzrClient({ apiKey: KEY, fetch });
  const hook = await client.webhooks.create({ url: 'https://example.com/hook', eventTypes: ['device.offline'] });
  const call = fetch.calls[0]!;
  assert.equal(call.url.origin, 'https://app.pulzr.net');
  assert.equal(call.headers.get('x-active-org'), null);
  assert.equal(call.headers.get('content-type'), 'application/json');
  assert.deepEqual(call.body, { url: 'https://example.com/hook', eventTypes: ['device.offline'] });
  assert.equal(hook.secret, 'whsec_x');
});

test('204 resolves to undefined', async () => {
  const fetch = mockFetch(() => new Response(null, { status: 204 }));
  const client = new PulzrClient({ apiKey: KEY, fetch });
  assert.equal(await client.webhooks.delete('w1'), undefined);
  assert.equal(fetch.calls[0]!.method, 'DELETE');
});

test('path segments are encoded', async () => {
  const fetch = mockFetch(() => json({}));
  const client = new PulzrClient({ apiKey: KEY, fetch });
  await client.webhooks.get('../agents');
  assert.equal(fetch.calls[0]!.url.pathname, '/api/v1/webhooks/..%2Fagents');
});

test('statuses map to error classes with message, details and body', async () => {
  const cases: Array<[number, new (...args: never[]) => PulzrError]> = [
    [400, ValidationError],
    [422, ValidationError],
    [401, AuthenticationError],
    [403, PermissionDeniedError],
    [404, NotFoundError],
    [409, ConflictError],
    [429, RateLimitError],
    [500, ServerError],
    [503, ServerError],
  ];
  for (const [status, kind] of cases) {
    const body = { error: `status ${status}`, details: ['a: bad'] };
    const client = new PulzrClient({ apiKey: KEY, maxRetries: 0, fetch: mockFetch(() => json(body, status)) });
    await assert.rejects(client.webhooks.list(), (error: unknown) => {
      assert.ok(error instanceof kind, `${status} -> ${(error as Error).name}`);
      assert.ok(error instanceof PulzrError);
      assert.equal(error.status, status);
      assert.equal(error.message, `status ${status}`);
      assert.deepEqual(error.details, ['a: bad']);
      assert.deepEqual(error.body, body);
      return true;
    });
  }
});

test('a quota refusal keeps resource and limit on the body', async () => {
  const body = { error: 'Device quota reached', resource: 'devices', limit: 50 };
  const client = new PulzrClient({ apiKey: KEY, fetch: mockFetch(() => json(body, 409)) });
  const error = await client.devices.provision({ devEui: '0'.repeat(16), appKey: '0'.repeat(32), deviceProfile: 'p' })
    .catch((e: unknown) => e);
  assert.ok(error instanceof ConflictError);
  assert.deepEqual(error.body, body);
});

test('a non-JSON error body becomes the message', async () => {
  const fetch = mockFetch(() => new Response('Bad Gateway', { status: 502 }));
  const client = new PulzrClient({ apiKey: KEY, maxRetries: 0, fetch });
  await assert.rejects(client.quantities.list(), (e: unknown) => e instanceof ServerError && e.message === 'Bad Gateway');
});

test('GET is retried after 503 and succeeds', async () => {
  const fetch = mockFetch((_, i) => (i < 2 ? json({ error: 'busy' }, 503, { 'Retry-After': '0' }) : json({ result: [] })));
  const client = new PulzrClient({ apiKey: KEY, fetch });
  assert.deepEqual(await client.quantities.list(), []);
  assert.equal(fetch.calls.length, 3);
});

test('GET gives up after maxRetries and throws the last error', async () => {
  const fetch = mockFetch(() => json({ error: 'busy' }, 503, { 'Retry-After': '0' }));
  const client = new PulzrClient({ apiKey: KEY, maxRetries: 1, fetch });
  await assert.rejects(client.quantities.list(), ServerError);
  assert.equal(fetch.calls.length, 2);
});

test('POST and PATCH are never retried', async () => {
  const fetch = mockFetch(() => json({ error: 'busy' }, 503, { 'Retry-After': '0' }));
  const client = new PulzrClient({ apiKey: KEY, maxRetries: 5, fetch });
  await assert.rejects(client.webhooks.test('w1'), ServerError);
  assert.equal(fetch.calls.length, 1);
  await assert.rejects(client.webhooks.update('w1', { enabled: false }), ServerError);
  assert.equal(fetch.calls.length, 2);
});

test('PUT and DELETE are retried', async () => {
  const fetch = mockFetch((_, i) => (i % 2 === 0 ? json({ error: 'busy' }, 502, { 'Retry-After': '0' }) : json({})));
  const client = new PulzrClient({ apiKey: KEY, fetch });
  await client.deviceTypes.setQuantities('t1', { temp: { quantity: 'temperature', unit: 'C' } });
  await client.devices.flushDownlinks('a840410000000001');
  assert.deepEqual(fetch.calls.map((c) => c.method), ['PUT', 'PUT', 'DELETE', 'DELETE']);
});

test('4xx other than 429 is not retried', async () => {
  const fetch = mockFetch(() => json({ error: 'nope' }, 404));
  const client = new PulzrClient({ apiKey: KEY, fetch });
  await assert.rejects(client.webhooks.get('w1'), NotFoundError);
  assert.equal(fetch.calls.length, 1);
});

test('Retry-After is honoured on 429', async () => {
  const fetch = mockFetch((_, i) => (i === 0 ? json({ error: 'slow down' }, 429, { 'Retry-After': '1' }) : json({ result: [] })));
  const client = new PulzrClient({ apiKey: KEY, fetch });
  const started = Date.now();
  await client.webhooks.list();
  const waited = Date.now() - started;
  assert.equal(fetch.calls.length, 2);
  assert.ok(waited >= 950, `waited ${waited} ms`);
});

test('a Retry-After longer than a minute is thrown, not slept on', async () => {
  const fetch = mockFetch(() => json({ error: 'slow down' }, 429, { 'Retry-After': '600' }));
  const client = new PulzrClient({ apiKey: KEY, fetch });
  const error = await client.webhooks.list().catch((e: unknown) => e);
  assert.ok(error instanceof RateLimitError);
  assert.equal(error.retryAfter, 600);
  assert.equal(fetch.calls.length, 1);
});

test('a network error on GET is retried, then thrown as ConnectionError', async () => {
  const fetch = mockFetch(() => {
    throw new TypeError('fetch failed');
  });
  const client = new PulzrClient({ apiKey: KEY, maxRetries: 1, fetch });
  const error = await client.webhooks.list().catch((e: unknown) => e);
  assert.ok(error instanceof ConnectionError);
  assert.equal(error.status, undefined);
  assert.ok(error.cause instanceof TypeError);
  assert.equal(fetch.calls.length, 2);
});

test('timeoutMs aborts a slow request as a ConnectionError', async () => {
  const fetch = mockFetch((call) => new Promise<Response>((_, reject) => {
    call.signal!.addEventListener('abort', () => reject(call.signal!.reason));
  }));
  const client = new PulzrClient({ apiKey: KEY, timeoutMs: 20, maxRetries: 0, fetch });
  const error = await client.webhooks.list().catch((e: unknown) => e);
  assert.ok(error instanceof ConnectionError);
  assert.match(error.message, /Timed out/);
});

test("the caller's abort is rethrown as it came, not retried", async () => {
  const fetch = mockFetch((call) => new Promise<Response>((_, reject) => {
    call.signal!.addEventListener('abort', () => reject(call.signal!.reason));
  }));
  const client = new PulzrClient({ apiKey: KEY, timeoutMs: 10_000, fetch });
  const controller = new AbortController();
  const pending = client.webhooks.list({ signal: controller.signal });
  controller.abort(new Error('stop'));
  await assert.rejects(pending, /stop/);
  assert.equal(fetch.calls.length, 1);
});

test('backoff grows and stays jittered within half to all of its ceiling', () => {
  assert.equal(backoff(0, () => 0), 250);
  assert.equal(backoff(0, () => 1), 500);
  assert.equal(backoff(3, () => 1), 4000);
  assert.equal(backoff(10, () => 1), 8000);
});

test('downlink bytes are sent as base64', async () => {
  const fetch = mockFetch(() => json({ id: 'q1' }, 201));
  const client = new PulzrClient({ apiKey: KEY, fetch });
  await client.devices.sendDownlink('a840410000000001', { fPort: 2, data: new Uint8Array([1, 2, 255]) });
  assert.deepEqual(fetch.calls[0]!.body, { fPort: 2, confirmed: false, data: 'AQL/' });
});

test('an apiKey is required', () => {
  assert.throws(() => new PulzrClient({ apiKey: '' }), PulzrError);
});

test('sql posts the query, and the limit only when given', async () => {
  const result = { columns: [{ name: 'n', type: 'integer' }], rows: [[1]], rowCount: 1, truncated: false, elapsedMs: 3 };
  const fetch = mockFetch(() => json(result));
  const client = new PulzrClient({ apiKey: KEY, fetch });
  assert.deepEqual((await client.sql('select 1 as n', { limit: 5000 })).rows, [[1]]);
  await client.sql('select 1 as n');
  assert.equal(fetch.calls[0]!.method, 'POST');
  assert.equal(fetch.calls[0]!.url.pathname, '/api/v1/sql');
  assert.deepEqual(fetch.calls[0]!.body, { query: 'select 1 as n', limit: 5000 });
  assert.deepEqual(fetch.calls[1]!.body, { query: 'select 1 as n' });
});

test('a refused query is a ValidationError with the position on its body', async () => {
  const fetch = mockFetch(() => json({ error: 'column "foo" does not exist', position: 8 }, 400));
  const client = new PulzrClient({ apiKey: KEY, fetch });
  await assert.rejects(client.sql('select foo from devices'), (error: unknown) =>
    error instanceof ValidationError && (error.body as { position: number }).position === 8);
  assert.equal(fetch.calls.length, 1);
});
