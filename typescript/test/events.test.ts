import assert from 'node:assert/strict';
import { test } from 'node:test';

import { AuthenticationError, ConnectionError, PulzrClient, type AnyEvent } from '../src/index.js';
import { KEY, collect, json, mockFetch, sse } from './helpers.js';

function event(n: number, type: AnyEvent['type'] = 'device.offline'): AnyEvent {
  return {
    id: `evt_${String(n).padStart(26, '0')}`,
    type,
    apiVersion: '2026-10-01',
    createdAt: '2026-10-13T14:02:11.402Z',
    org: 'usc',
    subject: 'a84041000181c061',
    data: {
      device: { devEui: 'a84041000181c061', name: 'Lot B 14', applicationId: null, deviceTypeId: null },
      lastSeen: '2026-10-12T14:02:11.402Z',
      changedAt: '2026-10-13T14:02:11.402Z',
      offlineAfterMinutes: 1440,
    },
  } as AnyEvent;
}

test('iterate pages forward with `after` until caught up', async () => {
  const pages = [
    { result: [event(1), event(2)], next: 'c2', hasMore: true },
    { result: [event(3)], next: 'c3', hasMore: true },
    { result: [], next: 'c3', hasMore: false },
  ];
  const fetch = mockFetch((_, i) => json(pages[i]));
  const client = new PulzrClient({ apiKey: KEY, fetch });
  const seen = await collect(client.events.iterate({ types: ['device.offline', 'device.online'], limit: 2 }));

  assert.deepEqual(seen.map((e) => e.id.slice(-1)), ['1', '2', '3']);
  assert.deepEqual(fetch.calls.map((c) => c.url.searchParams.get('after')), [null, 'c2', 'c3']);
  for (const call of fetch.calls) {
    assert.equal(call.url.pathname, '/api/v1/events');
    assert.equal(call.url.searchParams.get('types'), 'device.offline,device.online');
    assert.equal(call.url.searchParams.get('limit'), '2');
  }
});

test('iterate pages backward with `before` and stops at next: null', async () => {
  const pages = [
    { result: [event(3), event(2)], next: 'c2', hasMore: true },
    { result: [event(1)], next: null, hasMore: false },
  ];
  const fetch = mockFetch((_, i) => json(pages[i]));
  const client = new PulzrClient({ apiKey: KEY, fetch });
  const seen = await collect(client.events.iterate({ before: 'now' }));
  assert.equal(seen.length, 3);
  assert.deepEqual(fetch.calls.map((c) => c.url.searchParams.get('before')), ['now', 'c2']);
  assert.equal(fetch.calls[1]!.url.searchParams.has('after'), false);
});

test('events narrow by type', async () => {
  const fetch = mockFetch(() => json(event(1)));
  const client = new PulzrClient({ apiKey: KEY, fetch });
  const got = await client.events.get('evt_1');
  if (got.type === 'device.offline') {
    const minutes: number | null = got.data.offlineAfterMinutes;
    assert.equal(minutes, 1440);
  } else {
    assert.fail('expected device.offline');
  }
});

test('stream resumes with Last-Event-ID after a drop, honouring retry:', async () => {
  const controller = new AbortController();
  const fetch = mockFetch((call, i) => {
    if (i === 0) {
      return sse([
        'retry: 5\n',
        'event: ready\nid: c0\ndata: {"cursor":"c0"}\n\n',
        `id: c1\ndata: ${JSON.stringify(event(1))}\n\n`,
        ': keep-alive\n\n',
      ]);
    }
    if (i === 1) {
      // A server error: reconnect again, from the same cursor.
      return json({ error: 'busy' }, 503);
    }
    return sse([`id: c2\ndata: ${JSON.stringify(event(2))}\n\n`], { hold: call.signal! });
  });
  const client = new PulzrClient({ apiKey: KEY, org: 'usc', fetch });
  const stream = client.events.stream({ types: ['device.offline'], after: 'start', signal: controller.signal });

  const started = Date.now();
  const seen: string[] = [];
  for await (const e of stream) {
    seen.push(e.id);
    if (seen.length === 2) controller.abort();
  }
  assert.deepEqual(seen, [event(1).id, event(2).id]);
  assert.equal(stream.cursor, 'c2');
  assert.equal(fetch.calls.length, 3);

  const [first, second, third] = fetch.calls;
  assert.equal(first!.url.pathname, '/api/v1/events/stream');
  assert.equal(first!.url.searchParams.get('after'), 'start');
  assert.equal(first!.url.searchParams.get('types'), 'device.offline');
  assert.equal(first!.headers.get('last-event-id'), null);
  assert.equal(first!.headers.get('accept'), 'text/event-stream');
  for (const call of [second!, third!]) {
    assert.equal(call.headers.get('last-event-id'), 'c1');
    assert.equal(call.url.searchParams.has('after'), false);
    assert.equal(call.url.searchParams.get('types'), 'device.offline');
  }
  // retry: 5 ms, then a backed-off second attempt: well under the 3 s default.
  assert.ok(Date.now() - started < 2500);
});

test('stream starts from lastEventId and treats `event: error` as a drop', async () => {
  const controller = new AbortController();
  const fetch = mockFetch((call, i) => i === 0
    ? sse(['retry: 1\n', 'event: error\ndata: {"error":"The stream stopped"}\n\n'])
    : sse([`id: c9\ndata: ${JSON.stringify(event(9))}\n\n`], { hold: call.signal! }));
  const client = new PulzrClient({ apiKey: KEY, fetch });
  const stream = client.events.stream({ lastEventId: 'c8', signal: controller.signal });
  for await (const e of stream) {
    assert.equal(e.id, event(9).id);
    controller.abort();
  }
  assert.deepEqual(fetch.calls.map((c) => c.headers.get('last-event-id')), ['c8', 'c8']);
});

test('the ready event gives a resume point before any event arrives', async () => {
  const fetch = mockFetch((_, i) => i === 0
    ? sse(['retry: 1\nevent: ready\nid: c5\ndata: {"cursor":"c5"}\n\n'])
    : json({ error: 'gone' }, 401));
  const client = new PulzrClient({ apiKey: KEY, fetch });
  const stream = client.events.stream();
  await assert.rejects(collect(stream), AuthenticationError);
  assert.equal(stream.cursor, 'c5');
  assert.equal(fetch.calls[1]!.headers.get('last-event-id'), 'c5');
});

test('a refusal is thrown, not reconnected', async () => {
  const fetch = mockFetch(() => json({ error: 'Unknown or revoked API key' }, 401));
  const client = new PulzrClient({ apiKey: KEY, fetch });
  await assert.rejects(collect(client.events.stream()), AuthenticationError);
  assert.equal(fetch.calls.length, 1);
});

test('maxReconnects bounds a stream that keeps failing', async () => {
  const fetch = mockFetch(() => {
    throw new TypeError('fetch failed');
  });
  const client = new PulzrClient({ apiKey: KEY, fetch });
  // Each failure waits; a retry from the server never came, so shorten it by
  // stopping after the first reconnect.
  const stream = client.events.stream({ maxReconnects: 0 });
  await assert.rejects(collect(stream), ConnectionError);
  assert.equal(fetch.calls.length, 1);
});

test("the server's hourly `end` resumes at once from the cursor it names", async () => {
  const controller = new AbortController();
  const fetch = mockFetch((call, i) => i === 0
    ? sse([`id: c1\ndata: ${JSON.stringify(event(1))}\n\n`, 'event: end\nid: c4\ndata: {"reason":"deadline"}\n\n'])
    : sse([`id: c5\ndata: ${JSON.stringify(event(5))}\n\n`], { hold: call.signal! }));
  const client = new PulzrClient({ apiKey: KEY, fetch });
  const stream = client.events.stream({ signal: controller.signal });
  const started = Date.now();
  const seen: string[] = [];
  for await (const e of stream) {
    seen.push(e.id);
    if (seen.length === 2) controller.abort();
  }
  assert.equal(seen.length, 2);
  assert.equal(fetch.calls[1]!.headers.get('last-event-id'), 'c4');
  // No retry: was sent, so a wait would have been the 3 s default.
  assert.ok(Date.now() - started < 1000);
});

test('a 429 for too many streams waits its Retry-After', async () => {
  const controller = new AbortController();
  const fetch = mockFetch((call, i) => {
    if (i === 0) return sse(['retry: 1\nevent: ready\nid: c0\ndata: {"cursor":"c0"}\n\n']);
    if (i === 1) return json({ error: 'This organization already has 5 live streams open' }, 429, { 'Retry-After': '2' });
    return sse([`id: c1\ndata: ${JSON.stringify(event(1))}\n\n`], { hold: call.signal! });
  });
  const client = new PulzrClient({ apiKey: KEY, fetch });
  const started = Date.now();
  for await (const _ of client.events.stream({ signal: controller.signal })) controller.abort();
  // Without Retry-After the second wait would be at most a second of backoff.
  assert.ok(Date.now() - started >= 1950);
  assert.equal(fetch.calls.length, 3);
  assert.equal(fetch.calls[2]!.headers.get('last-event-id'), 'c0');
});
