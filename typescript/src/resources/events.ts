import { backoff, sleep, type Core } from '../core.js';
import { ConnectionError, PulzrError, RateLimitError, ServerError } from '../errors.js';
import type { AnyEvent, EventType } from '../events.js';
import { SSEDecoder, readSSE } from '../sse.js';
import type { EventPage, EventQuery, EventTypeInfo } from '../types.js';
import { seg } from '../util.js';

export interface StreamOptions {
  types?: EventType[];
  subject?: string;
  /** Start after this cursor. With neither this nor `lastEventId`, the stream
   *  starts at the end of the log: what happens next. */
  after?: string;
  /** Resume after this cursor, as a reconnecting EventSource would. */
  lastEventId?: string;
  signal?: AbortSignal;
  /** Give up after this many reconnects in a row with nothing received. Default: never. */
  maxReconnects?: number;
}

/**
 * The event log as it happens. Iterate it with `for await`; `cursor` is the
 * position after the last event yielded, to persist and pass back as
 * `lastEventId` after a restart.
 *
 * Reconnects by itself after a dropped connection, a server error, a 429
 * (after its Retry-After) or the server's hourly close, resuming exactly
 * where it stopped, so nothing is skipped and nothing repeats. A refusal that will not change on retry -- a bad key, a
 * missing scope, an unknown event type -- is thrown.
 */
export class EventStream implements AsyncIterable<AnyEvent> {
  /** Where to resume: after the last event yielded, or past events the
   *  filter skipped since. Undefined until the stream has opened. */
  cursor: string | undefined;

  constructor(
    private readonly core: Core,
    private readonly options: StreamOptions,
  ) {
    this.cursor = options.lastEventId;
  }

  async *[Symbol.asyncIterator](): AsyncGenerator<AnyEvent, void, undefined> {
    const { signal } = this.options;
    // The server's `retry:` says how soon to come back; this is EventSource's
    // own default until it does.
    let retryMs = 3000;
    let failures = 0;

    while (!signal?.aborted) {
      const decoder = new SSEDecoder();
      let failure: unknown;
      let ended = false;
      try {
        const response = await this.core.open('GET', '/api/v1/events/stream', {
          query: {
            types: this.options.types,
            subject: this.options.subject,
            // A cursor in hand wins over the starting point it came from.
            after: this.cursor === undefined ? this.options.after : undefined,
          },
          headers: this.cursor === undefined ? {} : { 'Last-Event-ID': this.cursor },
          maxRetries: 0,
          ...(signal ? { signal } : {}),
        });
        if (!response.body) throw new ConnectionError('The event stream has no body');

        for await (const message of readSSE(response.body, decoder)) {
          if (decoder.retry !== undefined) retryMs = decoder.retry;
          if (message.event === 'ready') {
            if (message.id) this.cursor = message.id;
            failures = 0;
            continue;
          }
          // The server closes every stream after an hour, saying where it
          // stopped; coming straight back is the expected answer.
          if (message.event === 'end') {
            if (message.id) this.cursor = message.id;
            ended = true;
            break;
          }
          if (message.event === 'error') {
            failure = new ServerError(errorText(message.data));
            break;
          }
          if (message.event !== 'message') continue;
          const event = JSON.parse(message.data) as AnyEvent;
          if (message.id) this.cursor = message.id;
          failures = 0;
          yield event;
        }
      } catch (error) {
        if (signal?.aborted) return;
        if (!retryable(error)) throw error;
        failure = error;
      }
      if (decoder.retry !== undefined) retryMs = decoder.retry;
      if (ended) {
        failures = 0;
        continue;
      }

      failures++;
      if (this.options.maxReconnects !== undefined && failures > this.options.maxReconnects) {
        throw failure instanceof PulzrError
          ? failure
          : new ConnectionError('The event stream kept closing', { cause: failure });
      }
      // The first reconnect waits what the server asked; a server that keeps
      // refusing is backed off from rather than hammered.
      let wait = failures === 1 ? retryMs : Math.max(retryMs, backoff(failures - 1));
      // Refused for too many open streams: the server says when a slot frees.
      if (failure instanceof RateLimitError && failure.retryAfter !== undefined) {
        wait = Math.max(wait, failure.retryAfter * 1000);
      }
      try {
        await sleep(wait, signal);
      } catch {
        return;
      }
    }
  }
}

// Anything not from the API is the connection breaking mid-body (fetch
// implementations disagree on what they throw for that), except an event
// that is not JSON, which no reconnect will fix.
function retryable(error: unknown): boolean {
  if (error instanceof PulzrError) {
    return error instanceof ConnectionError || error instanceof ServerError || error instanceof RateLimitError;
  }
  return !(error instanceof SyntaxError);
}

function errorText(data: string): string {
  try {
    const parsed = JSON.parse(data) as { error?: unknown };
    if (typeof parsed.error === 'string') return parsed.error;
  } catch {
    // Not JSON: the text is the message.
  }
  return data || 'The event stream stopped';
}

export class Events {
  constructor(private readonly core: Core) {}

  /** One page of the log. `after` reads oldest first; `before` (or `now`) newest first. */
  list(query: EventQuery = {}, opts: { signal?: AbortSignal } = {}): Promise<EventPage> {
    return this.core.request('GET', '/api/v1/events', { ...opts, query: { ...query } });
  }

  /**
   * Every event matching the query, page after page. Reading forward it stops
   * once caught up with the log; run it again later from the last event's
   * page cursor, or use `stream` to wait for new ones.
   */
  async *iterate(query: EventQuery = {}, opts: { signal?: AbortSignal } = {}): AsyncGenerator<AnyEvent, void, undefined> {
    let page = await this.list(query, opts);
    while (true) {
      yield* page.result;
      if (!page.hasMore || page.next === null) return;
      const next = query.before !== undefined ? { ...query, before: page.next } : { ...query, after: page.next };
      page = await this.list(next, opts);
    }
  }

  get(id: string, opts: { signal?: AbortSignal } = {}): Promise<AnyEvent> {
    return this.core.request('GET', `/api/v1/events/${seg(id)}`, opts);
  }

  async types(opts: { signal?: AbortSignal } = {}): Promise<{ result: EventTypeInfo[]; apiVersion: string }> {
    return this.core.request('GET', '/api/v1/events/types', opts);
  }

  /** See EventStream. Nothing is requested until iteration starts. */
  stream(options: StreamOptions = {}): EventStream {
    return new EventStream(this.core, options);
  }
}
