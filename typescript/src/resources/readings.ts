import type { Core } from '../core.js';
import type { LatestQuery, LatestReadings, Quantity, Series, SeriesQuery } from '../types.js';

export class Readings {
  constructor(private readonly core: Core) {}

  /** Each device's newest canonical readings. With `quantity`, only devices
   *  that have reported it, from the newest uplink that carried it. */
  async latest(query: LatestQuery = {}, opts: { signal?: AbortSignal } = {}): Promise<LatestReadings[]> {
    const page = await this.core.request<{ result: LatestReadings[] }>(
      'GET', '/api/v1/readings/latest', { ...opts, query: { ...query } });
    return page.result;
  }

  /** One quantity over time, bucketed, across every vendor that reports it. */
  series(query: SeriesQuery, opts: { signal?: AbortSignal } = {}): Promise<Series> {
    return this.core.request('GET', '/api/v1/readings', { ...opts, query: { ...query } });
  }
}

export class Quantities {
  constructor(private readonly core: Core) {}

  /** The canonical vocabulary, with how many of this org's devices report each. */
  async list(opts: { signal?: AbortSignal } = {}): Promise<Quantity[]> {
    const page = await this.core.request<{ result: Quantity[] }>('GET', '/api/v1/quantities', opts);
    return page.result;
  }
}
