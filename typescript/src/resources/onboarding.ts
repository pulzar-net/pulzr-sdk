import type { Core } from '../core.js';
import type {
  CatalogHit,
  DryRunResult,
  OnboardingAccept,
  OnboardingDevicesInput,
  OnboardingMetrics,
  OnboardingSession,
  OnboardingStart,
  OnboardingWatchEvent,
  RegisterResult,
} from '../types.js';
import { base64, seg } from '../util.js';
import { namedEvents } from './stream.js';

const WATCH_EVENTS = new Set(['session', 'join', 'uplink', 'first_uplink', 'end']);

export class Onboarding {
  constructor(private readonly core: Core) {}

  /** Models this org can use without generating a decoder; with `q`, The
   *  Things Network's device repository too. */
  catalog(q?: string, opts: { signal?: AbortSignal } = {}): Promise<{ result: CatalogHit[]; repositoryError: string | null }> {
    return this.core.request('GET', '/api/v1/onboarding/catalog', { ...opts, query: { q } });
  }

  /** The newest 50. */
  async sessions(opts: { signal?: AbortSignal } = {}): Promise<OnboardingSession[]> {
    const page = await this.core.request<{ result: OnboardingSession[] }>('GET', '/api/v1/onboarding/sessions', opts);
    return page.result;
  }

  /**
   * From a catalog hit, from a datasheet and/or a label photo, or from a
   * vendor and model with the payload format the board speaks. Returns at
   * once in `identifying`; follow it with `get` or `watch`. Generating a
   * decoder (anything but a catalog hit) is for org admins. RateLimitError
   * while five of the org's sessions are still working.
   */
  start(input: OnboardingStart, opts: { signal?: AbortSignal } = {}): Promise<OnboardingSession> {
    const body: Record<string, unknown> = { ...input };
    if (input.datasheetPdf !== undefined) body.datasheetPdf = base64(input.datasheetPdf);
    if (input.labelPhoto !== undefined) body.labelPhoto = base64(input.labelPhoto);
    return this.core.request('POST', '/api/v1/onboarding/sessions', { ...opts, body });
  }

  get(sessionId: string, opts: { signal?: AbortSignal } = {}): Promise<OnboardingSession> {
    return this.core.request('GET', `/api/v1/onboarding/sessions/${seg(sessionId)}`, opts);
  }

  /** Accept a `ready` decoder: creates the type, commit and device profile. Org admin. */
  accept(sessionId: string, input: OnboardingAccept = {}, opts: { signal?: AbortSignal } = {}): Promise<OnboardingSession> {
    return this.core.request('POST', `/api/v1/onboarding/sessions/${seg(sessionId)}/accept`, { ...opts, body: input });
  }

  /**
   * Register devices of this model. With `dryRun`, the rows are parsed and
   * returned (keys included) and nothing is registered -- how a scanned QR
   * code or a photographed label is checked first.
   */
  registerDevices(
    sessionId: string,
    input: OnboardingDevicesInput & { dryRun: true },
    opts?: { signal?: AbortSignal },
  ): Promise<DryRunResult>;
  registerDevices(
    sessionId: string,
    input: OnboardingDevicesInput & { dryRun?: false },
    opts?: { signal?: AbortSignal },
  ): Promise<RegisterResult>;
  registerDevices(
    sessionId: string,
    input: OnboardingDevicesInput & { dryRun?: boolean },
    opts: { signal?: AbortSignal } = {},
  ): Promise<DryRunResult | RegisterResult> {
    const body: Record<string, unknown> = { ...input };
    if (input.labelPhoto !== undefined) body.labelPhoto = base64(input.labelPhoto);
    return this.core.request('POST', `/api/v1/onboarding/sessions/${seg(sessionId)}/devices`, { ...opts, body });
  }

  abandon(sessionId: string, opts: { signal?: AbortSignal } = {}): Promise<OnboardingSession> {
    return this.core.request('POST', `/api/v1/onboarding/sessions/${seg(sessionId)}/abandon`, opts);
  }

  /** Started to first decoded uplink over 30 days: median and p90 seconds. */
  metrics(opts: { signal?: AbortSignal } = {}): Promise<OnboardingMetrics> {
    return this.core.request('GET', '/api/v1/onboarding/metrics', opts);
  }

  /**
   * The session as it moves, then its devices joining and reporting. Joins
   * and uplinks since registration are replayed on connect. Ends after an
   * `end` event (failed, abandoned, or the server's one-hour limit); not
   * reconnected, because a reconnect replays them again. RateLimitError when
   * the server has too many streams open.
   */
  async *watch(sessionId: string, opts: { signal?: AbortSignal } = {}): AsyncGenerator<OnboardingWatchEvent, void, undefined> {
    const events = namedEvents<OnboardingWatchEvent>(
      this.core, 'GET', `/api/v1/onboarding/sessions/${seg(sessionId)}/watch`, WATCH_EVENTS, { ...opts, maxRetries: 0 });
    for await (const event of events) {
      yield event;
      if (event.type === 'end') return;
    }
  }
}
