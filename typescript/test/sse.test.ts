import assert from 'node:assert/strict';
import { test } from 'node:test';

import { SSEDecoder, readSSE } from '../src/sse.js';
import { byteStream, collect } from './helpers.js';

function parse(chunks: string[]) {
  const decoder = new SSEDecoder();
  const out = chunks.flatMap((c) => decoder.push(c));
  return { out, decoder };
}

test('one message with a name, an id and data', () => {
  const { out } = parse(['event: ready\nid: c1\ndata: {"cursor":"c1"}\n\n']);
  assert.deepEqual(out, [{ event: 'ready', data: '{"cursor":"c1"}', id: 'c1' }]);
});

test('unnamed messages are `message`, and the id persists until replaced', () => {
  const { out } = parse(['id: a\ndata: 1\n\ndata: 2\n\nid: b\ndata: 3\n\n']);
  assert.deepEqual(out.map((m) => [m.event, m.data, m.id]), [
    ['message', '1', 'a'],
    ['message', '2', 'a'],
    ['message', '3', 'b'],
  ]);
});

test('multi-line data joins with LF; one leading space only is removed', () => {
  const { out } = parse(['data: first\ndata:  second\ndata:third\n\n']);
  assert.equal(out[0]?.data, 'first\n second\nthird');
});

test('comments are ignored and a blank event dispatches nothing', () => {
  const { out } = parse([': keep-alive\n\n: ping\n\nevent: x\n\ndata: y\n\n']);
  // `event: x` with no data is dropped, and its name does not leak into the next.
  assert.deepEqual(out, [{ event: 'message', data: 'y', id: '' }]);
});

test('empty data line still dispatches an empty message', () => {
  const { out } = parse(['data:\n\n']);
  assert.deepEqual(out, [{ event: 'message', data: '', id: '' }]);
});

test('retry sets the reconnection delay; a non-number is ignored', () => {
  const { decoder } = parse(['retry: 3000\n', 'retry: soon\n', 'event: ready\ndata: {}\n\n']);
  assert.equal(decoder.retry, 3000);
});

test('a field without a colon is a field with an empty value', () => {
  const { out } = parse(['data\ndata\n\n']);
  assert.equal(out[0]?.data, '\n');
});

test('id containing NUL is ignored', () => {
  const { out } = parse(['id: good\n\nid: b\0d\ndata: x\n\n']);
  assert.equal(out[0]?.id, 'good');
});

test('CRLF, CR and LF line endings', () => {
  for (const nl of ['\r\n', '\r', '\n']) {
    const { out } = parse([`event: a${nl}data: 1${nl}data: 2${nl}${nl}data: 3${nl}${nl}`]);
    assert.deepEqual(out.map((m) => [m.event, m.data]), [['a', '1\n2'], ['message', '3']], JSON.stringify(nl));
  }
});

test('CRLF split across two chunks is one line ending, not a blank line', () => {
  const { out } = parse(['data: a\r', '\ndata: b\r\n\r\n']);
  assert.deepEqual(out.map((m) => m.data), ['a\nb']);
});

test('a CR at a chunk end followed by an empty chunk keeps its LF pairing', () => {
  const { out } = parse(['data: a\r', '', '\ndata: b\n\n']);
  assert.deepEqual(out.map((m) => m.data), ['a\nb']);
});

test('lines split at every possible point parse the same', () => {
  const text = 'retry: 10\r\nevent: ready\r\nid: c0\r\ndata: {"cursor":"c0"}\r\n\r\n: c\nid: c1\ndata: {"a":1}\n\n';
  const whole = parse([text]).out;
  for (let cut = 1; cut < text.length; cut++) {
    assert.deepEqual(parse([text.slice(0, cut), text.slice(cut)]).out, whole, `cut at ${cut}`);
  }
  assert.deepEqual(parse(text.split('')).out, whole);
});

test('a message without its blank line at the end of the stream is discarded', async () => {
  const out = await collect(readSSE(byteStream(['data: kept\n\ndata: cut off'])));
  assert.deepEqual(out.map((m) => m.data), ['kept']);
});

test('a leading BOM is stripped, from bytes and from text', async () => {
  const bom = new Uint8Array([0xef, 0xbb, 0xbf]);
  const out = await collect(readSSE(byteStream([bom, 'data: x\n\n'])));
  assert.deepEqual(out.map((m) => m.data), ['x']);
  assert.deepEqual(parse(['﻿data: y\n\n']).out.map((m) => m.data), ['y']);
  // Only the very first one: later it is data.
  assert.equal(parse(['data: a\n\n', '﻿data: b\n\n']).out.length, 1);
});

test('a BOM split across chunks is still stripped', async () => {
  const out = await collect(readSSE(byteStream([new Uint8Array([0xef]), new Uint8Array([0xbb, 0xbf]), 'data: x\n\n'])));
  assert.deepEqual(out.map((m) => m.data), ['x']);
});

test('multibyte UTF-8 split across chunks is reassembled', async () => {
  const bytes = new TextEncoder().encode('data: Bâtiment Zürich — 東 😀\n\n');
  const chunks: Uint8Array[] = [];
  for (let i = 0; i < bytes.length; i++) chunks.push(bytes.subarray(i, i + 1));
  const out = await collect(readSSE(byteStream(chunks)));
  assert.deepEqual(out.map((m) => m.data), ['Bâtiment Zürich — 東 😀']);
});

test('breaking out of the iteration cancels the stream', async () => {
  let cancelled = false;
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(new TextEncoder().encode('data: 1\n\ndata: 2\n\n'));
    },
    cancel() {
      cancelled = true;
    },
  });
  const out = await collect(readSSE(body), 1);
  assert.equal(out.length, 1);
  assert.equal(cancelled, true);
});
