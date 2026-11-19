/**
 * Verifying a webhook delivery. A mirror of shared/events.py `verify`, tested
 * against vectors that function produced (sdk/fixtures), so the three
 * implementations cannot drift apart without a test failing.
 *
 * `Parkeze-Signature: t=<unix seconds>,v1=<hex>[,v1=<hex>]`, each v1 an
 * HMAC-SHA256 of `<t>.<raw body>`. Two v1 values appear for a day after the
 * secret is rotated; any match is enough.
 */

import { WebhookSignatureError } from './errors.js';
import type { WebhookEvent } from './events.js';

export const SIGNATURE_HEADER = 'Parkeze-Signature';
export const EVENT_ID_HEADER = 'Parkeze-Event-Id';
export const EVENT_TYPE_HEADER = 'Parkeze-Event-Type';
export const TOLERANCE_SECONDS = 300;

export type RawBody = string | Uint8Array | ArrayBuffer;

export interface VerifyOptions {
  /** Seconds a signature's timestamp may be from `now`. Default 300. */
  tolerance?: number;
  /** Unix seconds; default the current time. */
  now?: number;
}

const encoder = new TextEncoder();

function bytesOf(body: RawBody): Uint8Array {
  if (typeof body === 'string') return encoder.encode(body);
  if (body instanceof Uint8Array) return body;
  return new Uint8Array(body);
}

/**
 * The verified body must be the bytes as received. A body parsed and
 * re-serialized -- `JSON.stringify(req.body)` -- differs in whitespace or key
 * order often enough that it will fail here, correctly.
 */
export async function verifyWebhook(
  secret: string | readonly string[],
  rawBody: RawBody,
  header: string,
  opts: VerifyOptions = {},
): Promise<boolean> {
  const parsed = parseHeader(header);
  if (!parsed) return false;
  const now = opts.now ?? Date.now() / 1000;
  const tolerance = opts.tolerance ?? TOLERANCE_SECONDS;
  if (Math.abs(now - Number(parsed.timestamp)) > tolerance) return false;
  if (parsed.signatures.length === 0) return false;

  const secrets = typeof secret === 'string' ? [secret] : [...secret];
  const prefix = encoder.encode(`${parsed.timestamp}.`);
  const body = bytesOf(rawBody);
  const message = new Uint8Array(prefix.length + body.length);
  message.set(prefix, 0);
  message.set(body, prefix.length);

  const subtle = await subtleCrypto();
  let matched = false;
  for (const s of secrets) {
    const key = await subtle.importKey('raw', encoder.encode(s), { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']);
    const expected = hex(new Uint8Array(await subtle.sign('HMAC', key, message)));
    for (const candidate of parsed.signatures) {
      // Every candidate is compared, without stopping at the first match, so
      // the time taken says nothing about which one matched.
      if (timingSafeEqual(expected, candidate)) matched = true;
    }
  }
  return matched;
}

/** The event in a delivery, once its signature is verified. Throws WebhookSignatureError. */
export async function constructEvent(
  secret: string | readonly string[],
  rawBody: RawBody,
  header: string | null | undefined,
  opts: VerifyOptions = {},
): Promise<WebhookEvent> {
  if (!header) throw new WebhookSignatureError(`No ${SIGNATURE_HEADER} header`);
  if (!(await verifyWebhook(secret, rawBody, header, opts))) {
    throw new WebhookSignatureError('The webhook signature did not verify');
  }
  const text = typeof rawBody === 'string' ? rawBody : new TextDecoder().decode(bytesOf(rawBody));
  try {
    return JSON.parse(text) as WebhookEvent;
  } catch (cause) {
    throw new WebhookSignatureError('The webhook body is not JSON', { cause });
  }
}

/**
 * `t` and every `v1`, or null where events.verify would return False: a part
 * without `=`, no `t`, or a `t` that Python's int() refuses. The timestamp is
 * returned as int() would print it, because that is what was signed.
 */
function parseHeader(header: string): { timestamp: string; signatures: string[] } | null {
  if (typeof header !== 'string') return null;
  const pairs: Array<[string, string]> = [];
  for (const part of header.split(',')) {
    const at = part.indexOf('=');
    if (at === -1) return null;
    pairs.push([part.slice(0, at), part.slice(at + 1)]);
  }
  // dict() keeps the last of a repeated key.
  const t = pairs.filter(([k]) => k === 't').pop()?.[1];
  if (t === undefined) return null;
  const trimmed = t.trim();
  if (!/^[+-]?\d+(_\d+)*$/.test(trimmed)) return null;
  const timestamp = BigInt(trimmed.replace(/_/g, '')).toString();
  return { timestamp, signatures: pairs.filter(([k]) => k === 'v1').map(([, v]) => v) };
}

function hex(bytes: Uint8Array): string {
  let out = '';
  for (const b of bytes) out += b.toString(16).padStart(2, '0');
  return out;
}

function timingSafeEqual(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

// Node 18 has WebCrypto but does not put it on globalThis without a flag.
// The specifier is a variable so a browser bundler does not try to resolve it.
// Only the imported one is cached: the global is cheap to read, and reading it
// each time keeps a test that hides it honest.
let imported: SubtleCrypto | undefined;
async function subtleCrypto(): Promise<SubtleCrypto> {
  const global = (globalThis as { crypto?: Crypto }).crypto;
  if (global?.subtle) return global.subtle;
  if (imported) return imported;
  const specifier = 'node:crypto';
  const mod = (await import(specifier)) as { webcrypto?: { subtle?: SubtleCrypto } };
  if (!mod.webcrypto?.subtle) throw new Error('No WebCrypto available to verify webhook signatures');
  return (imported = mod.webcrypto.subtle);
}
