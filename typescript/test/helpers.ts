import type { FetchLike } from '../src/index.js';

export interface Call {
  url: URL;
  method: string;
  headers: Headers;
  body: unknown;
  signal: AbortSignal | undefined;
}

/** A fetch that records each call and answers from `handler`. */
export function mockFetch(handler: (call: Call, index: number) => Response | Promise<Response>): FetchLike & { calls: Call[] } {
  const calls: Call[] = [];
  const fn = (async (input: string, init: RequestInit) => {
    const call: Call = {
      url: new URL(input),
      method: init.method ?? 'GET',
      headers: new Headers(init.headers),
      body: typeof init.body === 'string' ? JSON.parse(init.body) : undefined,
      signal: init.signal ?? undefined,
    };
    calls.push(call);
    return handler(call, calls.length - 1);
  }) as FetchLike & { calls: Call[] };
  fn.calls = calls;
  return fn;
}

export function json(body: unknown, status = 200, headers: Record<string, string> = {}): Response {
  return new Response(body === undefined ? null : JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json', ...headers },
  });
}

/** A body that yields these chunks (strings are UTF-8 encoded) and then
 *  closes, or stays open until the request is aborted when `hold` is set. */
export function byteStream(chunks: Array<string | Uint8Array>, opts: { hold?: AbortSignal } = {}): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  let i = 0;
  return new ReadableStream<Uint8Array>({
    pull(controller) {
      const chunk = chunks[i++];
      if (chunk !== undefined) {
        controller.enqueue(typeof chunk === 'string' ? encoder.encode(chunk) : chunk);
        return;
      }
      if (!opts.hold) {
        controller.close();
        return;
      }
      return new Promise<void>((resolve) => {
        const stop = () => {
          controller.error(new DOMException('aborted', 'AbortError'));
          resolve();
        };
        if (opts.hold!.aborted) stop();
        else opts.hold!.addEventListener('abort', stop, { once: true });
      });
    },
  });
}

export function sse(chunks: Array<string | Uint8Array>, opts: { hold?: AbortSignal; status?: number } = {}): Response {
  return new Response(byteStream(chunks, opts), {
    status: opts.status ?? 200,
    headers: { 'Content-Type': 'text/event-stream' },
  });
}

export async function collect<T>(iterable: AsyncIterable<T>, limit = Infinity): Promise<T[]> {
  const out: T[] = [];
  for await (const item of iterable) {
    out.push(item);
    if (out.length >= limit) break;
  }
  return out;
}

export const KEY = 'pzk_0123abcd_abcdefghijklmnopqrstuvwxyz0123';
