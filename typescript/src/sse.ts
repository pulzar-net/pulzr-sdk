/**
 * Server-Sent Events, parsed from a fetch body.
 *
 * Not EventSource: it cannot send an Authorization header, cannot POST (the
 * assistant's reply is the response to sending a message), and does not exist
 * in Node 18. The parsing rules are the HTML standard's, so a stream that works
 * in a browser's EventSource parses identically here.
 */

export interface SSEMessage {
  /** The `event:` name, or `message` when the server sent none. */
  event: string;
  data: string;
  /** The last event ID as of this message -- it persists across messages
   *  until the server sends another, which is what makes it a resume point. */
  id: string;
}

/**
 * Text in, messages out. Feed it decoded text in pieces of any size; a line
 * split across two pieces, or a CRLF split between them, comes out whole.
 */
export class SSEDecoder {
  /** The reconnection delay the server last asked for, in milliseconds. */
  retry: number | undefined;
  lastEventId = '';

  private buffer = '';
  private data: string[] = [];
  private hasData = false;
  private eventType = '';
  // A chunk that ended in CR may be the first half of CRLF; the LF that may
  // open the next chunk belongs to the line already ended, not a blank line.
  private afterCR = false;
  private started = false;

  push(text: string): SSEMessage[] {
    if (!this.started && text.length > 0) {
      this.started = true;
      if (text.charCodeAt(0) === 0xfeff) text = text.slice(1);
    }
    if (text.length === 0) return [];
    if (this.afterCR && text.startsWith('\n')) text = text.slice(1);
    this.afterCR = false;
    this.buffer += text;

    const out: SSEMessage[] = [];
    let start = 0;
    for (let i = 0; i < this.buffer.length; i++) {
      const ch = this.buffer.charCodeAt(i);
      if (ch !== 0x0a && ch !== 0x0d) continue;
      const line = this.buffer.slice(start, i);
      if (ch === 0x0d) {
        if (i + 1 < this.buffer.length) {
          if (this.buffer.charCodeAt(i + 1) === 0x0a) i++;
        } else {
          this.afterCR = true;
        }
      }
      start = i + 1;
      const message = this.line(line);
      if (message) out.push(message);
    }
    this.buffer = this.buffer.slice(start);
    return out;
  }

  /** End of stream. A message without its blank line is discarded, as the
   *  standard says: it may have been cut off mid-`data`. */
  end(): SSEMessage[] {
    this.buffer = '';
    this.data = [];
    this.hasData = false;
    this.eventType = '';
    return [];
  }

  private line(line: string): SSEMessage | undefined {
    if (line === '') return this.dispatch();
    if (line.startsWith(':')) return undefined;
    const colon = line.indexOf(':');
    const field = colon === -1 ? line : line.slice(0, colon);
    let value = colon === -1 ? '' : line.slice(colon + 1);
    if (value.startsWith(' ')) value = value.slice(1);

    switch (field) {
      case 'data':
        this.data.push(value);
        this.hasData = true;
        break;
      case 'event':
        this.eventType = value;
        break;
      case 'id':
        if (!value.includes('\0')) this.lastEventId = value;
        break;
      case 'retry':
        if (/^\d+$/.test(value)) this.retry = Number(value);
        break;
      default:
        break;
    }
    return undefined;
  }

  private dispatch(): SSEMessage | undefined {
    const message = this.hasData
      ? { event: this.eventType || 'message', data: this.data.join('\n'), id: this.lastEventId }
      : undefined;
    this.data = [];
    this.hasData = false;
    this.eventType = '';
    return message;
  }
}

/**
 * Messages from a byte stream. Decoding is streaming UTF-8, so a multibyte
 * character split across two network reads is reassembled rather than turned
 * into two replacement characters. Cancelling the iteration (a `break` in
 * `for await`) cancels the stream, which closes the connection.
 */
export async function* readSSE(
  body: ReadableStream<Uint8Array>,
  decoder: SSEDecoder = new SSEDecoder(),
): AsyncGenerator<SSEMessage, void, undefined> {
  const reader = body.getReader();
  const text = new TextDecoder('utf-8');
  let done = false;
  try {
    while (true) {
      const chunk = await reader.read();
      if (chunk.done) break;
      yield* decoder.push(text.decode(chunk.value, { stream: true }));
    }
    yield* decoder.push(text.decode());
    yield* decoder.end();
    done = true;
  } finally {
    if (!done) await reader.cancel().catch(() => undefined);
    reader.releaseLock();
  }
}
