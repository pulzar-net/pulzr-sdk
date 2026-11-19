/**
 * Every failure the client raises is a PulzrError, so one `instanceof`
 * catches all of them; the subclass says which kind without parsing a
 * message. The API answers `{error, details?}` with a status, and quota
 * refusals add `resource` and `limit` -- kept on `body` rather than promoted,
 * because they are the only fields not shared by every error.
 */
export class PulzrError extends Error {
  /** HTTP status, or undefined when no response arrived. */
  readonly status: number | undefined;
  /** `details` from the body: a list of problems for a validation error. */
  readonly details: unknown;
  /** The parsed response body, or its text when it was not JSON. */
  readonly body: unknown;
  readonly headers: Headers | undefined;

  constructor(
    message: string,
    init: { status?: number; details?: unknown; body?: unknown; headers?: Headers; cause?: unknown } = {},
  ) {
    super(message, init.cause === undefined ? undefined : { cause: init.cause });
    this.name = new.target.name;
    this.status = init.status;
    this.details = init.details;
    this.body = init.body;
    this.headers = init.headers;
  }
}

export class AuthenticationError extends PulzrError {}
export class PermissionDeniedError extends PulzrError {}
export class NotFoundError extends PulzrError {}
export class ConflictError extends PulzrError {}
export class ValidationError extends PulzrError {}
export class ServerError extends PulzrError {}

export class RateLimitError extends PulzrError {
  /** Seconds the server asked us to wait, when it said. */
  readonly retryAfter: number | undefined;

  constructor(message: string, init: ConstructorParameters<typeof PulzrError>[1] & { retryAfter?: number } = {}) {
    super(message, init);
    this.retryAfter = init.retryAfter;
  }
}

/** No response: DNS, refused connection, reset, or the client's own timeout. */
export class ConnectionError extends PulzrError {}

/** A webhook delivery whose signature did not verify; see `constructEvent`. */
export class WebhookSignatureError extends PulzrError {}

/** Seconds from a Retry-After header, which may be a delay or an HTTP date. */
export function parseRetryAfter(value: string | null | undefined, now = Date.now()): number | undefined {
  if (value == null || value.trim() === '') return undefined;
  const trimmed = value.trim();
  if (/^\d+(\.\d+)?$/.test(trimmed)) return Number(trimmed);
  const at = Date.parse(trimmed);
  if (Number.isNaN(at)) return undefined;
  return Math.max(0, (at - now) / 1000);
}

export function errorFromResponse(status: number, body: unknown, headers?: Headers): PulzrError {
  const object = body !== null && typeof body === 'object' ? (body as Record<string, unknown>) : undefined;
  const message =
    typeof object?.error === 'string' ? object.error
    : typeof body === 'string' && body.trim() !== '' && body.length < 500 ? body.trim()
    : `HTTP ${status}`;
  // middleware/auth.py says `detail` (a sentence) where every route says
  // `details` (a list); either way it is the part that says what to do.
  const details = object?.details ?? object?.detail;
  const init = { status, details, body, ...(headers ? { headers } : {}) };

  if (status === 400 || status === 422) return new ValidationError(message, init);
  if (status === 401) return new AuthenticationError(message, init);
  if (status === 403) return new PermissionDeniedError(message, init);
  if (status === 404) return new NotFoundError(message, init);
  if (status === 409) return new ConflictError(message, init);
  if (status === 429) {
    const retryAfter = parseRetryAfter(headers?.get('retry-after'));
    return new RateLimitError(message, { ...init, ...(retryAfter === undefined ? {} : { retryAfter }) });
  }
  if (status >= 500) return new ServerError(message, init);
  return new PulzrError(message, init);
}
