import type { Core, RequestOptions } from '../core.js';
import { readSSE } from '../sse.js';

/**
 * Named SSE events as `{type, data}`, data parsed as JSON. Names outside
 * `known` are skipped rather than passed through, so the union a caller
 * switches on stays exhaustive when the server adds an event.
 */
export async function* namedEvents<E extends { type: string; data: unknown }>(
  core: Core,
  method: string,
  path: string,
  known: ReadonlySet<string>,
  options: RequestOptions,
): AsyncGenerator<E, void, undefined> {
  const response = await core.open(method, path, options);
  if (!response.body) return;
  for await (const message of readSSE(response.body)) {
    if (!known.has(message.event)) continue;
    yield { type: message.event, data: JSON.parse(message.data) } as E;
  }
}
