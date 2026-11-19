import { ConnectionError, PulzrError, errorFromResponse, parseRetryAfter } from './errors.js';

export type FetchLike = (input: string, init: RequestInit) => Promise<Response>;

export interface ClientOptions {
  /** `pzk_...`, from API keys in the console. */
  apiKey: string;
  /** Org alias. A key acts for one org; naming another is refused with 403. */
  org?: string;
  /** Default `https://app.pulzr.net`. */
  baseUrl?: string;
  /** Default: the global `fetch`. */
  fetch?: FetchLike;
  /** Retries of an idempotent request after 429, 5xx or a network error. Default 2. */
  maxRetries?: number;
  /** Per request, until the response is read. For a stream, until its headers arrive. */
  timeoutMs?: number;
}

export type QueryValue = string | number | boolean | null | undefined | readonly string[];

export interface RequestOptions {
  query?: Record<string, QueryValue>;
  body?: unknown;
  signal?: AbortSignal;
  headers?: Record<string, string>;
  /** Override the client's retry count for this call. */
  maxRetries?: number;
}

// Only methods a repeat cannot double. A POST that timed out may have
// created the device, queued the downlink or started the run; sending it
// again would do it twice, so the caller decides.
const IDEMPOTENT = new Set(['GET', 'HEAD', 'PUT', 'DELETE', 'OPTIONS']);

// Longer than this and the request fails rather than sleeping: a caller that
// is told to come back in ten minutes should hear that, not hang.
const MAX_RETRY_AFTER_SECONDS = 60;

export function backoff(attempt: number, random: () => number = Math.random): number {
  const ceiling = Math.min(8000, 500 * 2 ** attempt);
  return Math.round(ceiling * (0.5 + random() * 0.5));
}

export function sleep(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) return reject(abortReason(signal));
    const timer = setTimeout(() => {
      signal?.removeEventListener('abort', onAbort);
      resolve();
    }, ms);
    const onAbort = () => {
      clearTimeout(timer);
      reject(abortReason(signal!));
    };
    signal?.addEventListener('abort', onAbort, { once: true });
  });
}

function abortReason(signal: AbortSignal): unknown {
  return signal.reason ?? new DOMException('The operation was aborted.', 'AbortError');
}

export class Core {
  readonly baseUrl: string;
  readonly maxRetries: number;
  private readonly apiKey: string;
  private readonly org: string | undefined;
  private readonly fetchImpl: FetchLike;
  private readonly timeoutMs: number | undefined;

  constructor(options: ClientOptions) {
    if (!options || typeof options.apiKey !== 'string' || options.apiKey === '') {
      throw new PulzrError('apiKey is required');
    }
    this.apiKey = options.apiKey;
    this.org = options.org;
    this.baseUrl = (options.baseUrl ?? 'https://app.pulzr.net').replace(/\/+$/, '');
    this.maxRetries = options.maxRetries ?? 2;
    this.timeoutMs = options.timeoutMs;
    if (!options.fetch && typeof globalThis.fetch !== 'function') {
      throw new PulzrError('No global fetch: pass one in options.fetch');
    }
    // Wrapped so a browser's fetch is never called with `this` set to the client.
    this.fetchImpl = options.fetch ?? ((input, init) => globalThis.fetch(input, init));
  }

  url(path: string, query?: Record<string, QueryValue>): string {
    const params = new URLSearchParams();
    for (const [key, value] of Object.entries(query ?? {})) {
      if (value === undefined || value === null) continue;
      if (Array.isArray(value)) {
        if (value.length) params.set(key, value.join(','));
      } else {
        params.set(key, String(value));
      }
    }
    const qs = params.toString();
    return `${this.baseUrl}${path}${qs ? `?${qs}` : ''}`;
  }

  headers(extra?: Record<string, string>, hasBody = false): Record<string, string> {
    const headers: Record<string, string> = {
      Authorization: `Bearer ${this.apiKey}`,
      Accept: 'application/json',
    };
    if (this.org) headers['X-Active-Org'] = this.org;
    if (hasBody) headers['Content-Type'] = 'application/json';
    return { ...headers, ...extra };
  }

  /** JSON in, JSON out. 204 resolves to undefined. */
  async request<T>(method: string, path: string, options: RequestOptions = {}): Promise<T> {
    const { response, timer } = await this.send(method, path, options);
    try {
      const text = await response.text();
      return (text === '' ? undefined : JSON.parse(text)) as T;
    } catch (error) {
      if (options.signal?.aborted) throw error;
      throw new ConnectionError('The response could not be read', { status: response.status, cause: error });
    } finally {
      timer.release();
    }
  }

  /** An open response whose body the caller reads, e.g. as SSE. */
  async open(method: string, path: string, options: RequestOptions = {}): Promise<Response> {
    const { response, timer } = await this.send(method, path, {
      ...options,
      headers: { Accept: 'text/event-stream', ...options.headers },
    });
    // The timeout covered connecting; a stream is meant to stay open. The
    // caller's signal still reaches the body, so it is not released.
    timer.stopTimer();
    return response;
  }

  /**
   * Send with retries. Resolves with a 2xx response and its timer; anything else is thrown as a PulzrError subclass, except
   * the caller's own abort, which is rethrown as it came.
   */
  private async send(
    method: string,
    path: string,
    options: RequestOptions,
  ): Promise<{ response: Response; timer: Timer }> {
    const url = this.url(path, options.query);
    const hasBody = options.body !== undefined;
    const init: RequestInit = {
      method,
      headers: this.headers(options.headers, hasBody),
      ...(hasBody ? { body: JSON.stringify(options.body) } : {}),
    };
    const retries = IDEMPOTENT.has(method) ? (options.maxRetries ?? this.maxRetries) : 0;

    for (let attempt = 0; ; attempt++) {
      const timer = this.timer(options.signal);
      let response: Response;
      try {
        response = await this.fetchImpl(url, { ...init, ...(timer.signal ? { signal: timer.signal } : {}) });
      } catch (cause) {
        timer.release();
        if (options.signal?.aborted) throw cause;
        const error = new ConnectionError(
          timer.timedOut() ? `Timed out after ${this.timeoutMs} ms` : `Could not reach ${this.baseUrl}`,
          { cause },
        );
        if (attempt < retries) {
          await sleep(backoff(attempt), options.signal);
          continue;
        }
        throw error;
      }

      if (response.ok) return { response, timer };

      let body: unknown;
      try {
        const text = await response.text();
        try {
          body = text === '' ? undefined : JSON.parse(text);
        } catch {
          body = text;
        }
      } catch {
        body = undefined;
      } finally {
        timer.release();
      }

      const error = errorFromResponse(response.status, body, response.headers);
      const retryable = response.status === 429 || response.status >= 500;
      if (retryable && attempt < retries) {
        const after = parseRetryAfter(response.headers.get('retry-after'));
        if (after === undefined || after <= MAX_RETRY_AFTER_SECONDS) {
          await sleep(after === undefined ? backoff(attempt) : after * 1000, options.signal);
          continue;
        }
      }
      throw error;
    }
  }

  /**
   * A signal that fires on the caller's abort or the client's timeout,
   * whichever is first. Built by hand because AbortSignal.any is newer than
   * Node 18.
   */
  private timer(outer?: AbortSignal): Timer {
    if (this.timeoutMs === undefined) {
      return { signal: outer, stopTimer: () => {}, release: () => {}, timedOut: () => false };
    }
    const controller = new AbortController();
    let expired = false;
    const timer = setTimeout(() => {
      expired = true;
      controller.abort(new DOMException('The request timed out.', 'TimeoutError'));
    }, this.timeoutMs);
    const forward = () => controller.abort(outer?.reason);
    if (outer?.aborted) forward();
    else outer?.addEventListener('abort', forward, { once: true });
    return {
      signal: controller.signal,
      stopTimer: () => clearTimeout(timer),
      release: () => {
        clearTimeout(timer);
        outer?.removeEventListener('abort', forward);
      },
      timedOut: () => expired,
    };
  }
}

interface Timer {
  signal: AbortSignal | undefined;
  stopTimer: () => void;
  /** Stop the timer and stop forwarding the caller's abort. */
  release: () => void;
  timedOut: () => boolean;
}
