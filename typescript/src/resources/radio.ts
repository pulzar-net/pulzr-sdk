/**
 * Airtime and fair use, solved locations, and coverage: net-api's
 * routes/airtime.py, routes/location.py and routes/coverage.py.
 */
import type { Core } from '../core.js';
import type { FairUsePolicy } from '../events.js';
import { seg } from '../util.js';

type Opts = { signal?: AbortSignal };

export interface AirtimeDay {
  /** A UTC day, YYYY-MM-DD. */
  day: string;
  uplinks: number;
  uplinkAirtimeMs: number;
  /** Uplinks with no airtime: stored before it was recorded, or a modulation the formula does not cover. */
  uplinksUnmeasured: number;
  downlinks: number;
  /** A floor: each downlink is priced as the empty frame. */
  downlinkAirtimeMs: number;
  /** Uplinks per spreading factor, keyed "7" to "12". */
  spreadingFactors: Record<string, number>;
  exceeded: Array<'uplinkAirtime' | 'downlinks'>;
  warnedAt: string | null;
}

export interface DeviceAirtime {
  devEui: string;
  policy: FairUsePolicy;
  today: AirtimeDay;
  days: AirtimeDay[];
  total: { uplinks: number; uplinkAirtimeMs: number; downlinks: number; downlinkAirtimeMs: number };
  spreadingFactors: Record<string, number>;
}

export interface OrgAirtime {
  day: string;
  policy: FairUsePolicy;
  devices: number;
  exceeding: number;
  result: Array<AirtimeDay & { devEui: string; name: string | null; share: number | null }>;
}

export interface SolvedPosition {
  latitude: number;
  longitude: number;
  source: 'solved';
  /** About a one-sigma radius, in metres. */
  accuracyM: number;
  method: 'tdoa' | 'rssi' | 'centroid';
  time: string;
  uplinks: number;
  /** Every gateway the solve used: Pulzar-operated or the org's own, never another org's. */
  gateways: Array<{ gatewayId: string; operator: 'parkeze' | 'org'; rssi: number; snr: number | null; fineTimestamp: boolean }>;
}

export interface ReportedPosition {
  latitude: number;
  longitude: number;
  source: 'device' | 'manual' | 'gateway';
  time?: string;
  gatewayId?: string;
  /** Only on a `manual` position: who set it. */
  setBy?: string | null;
}

export interface DeviceLocation {
  devEui: string;
  /** The device's own fix, else the hand-set one, else the solved position, else its gateway's. */
  location: ReportedPosition | SolvedPosition | null;
  reported: ReportedPosition | null;
  manual: ReportedPosition | null;
  solved: SolvedPosition | null;
  gateway: ReportedPosition | null;
  history: SolvedPosition[];
}

export interface CoverageCellProperties {
  cell: string;
  rssi: number;
  rssiMax: number;
  snr: number | null;
  samples: number;
  grade: 'good' | 'fair' | 'weak' | null;
  gateways: number;
  /** Not in the public layer. */
  gatewayId?: string;
  lastAt?: string;
  /** Only in the public layer: YYYY-MM. */
  lastMonth?: string;
}

export interface CoverageCollection {
  type: 'FeatureCollection';
  resolution: number;
  truncated: boolean;
  features: Array<{
    type: 'Feature';
    id: string;
    geometry: { type: 'Polygon'; coordinates: number[][][] };
    properties: CoverageCellProperties;
  }>;
}

export interface CoverageSignal {
  gatewayId: string;
  samples: number;
  rssi: number;
  rssiMax: number;
  snr: number | null;
  snrMax: number | null;
  firstAt: string;
  lastAt: string;
}

export interface CoverageAt {
  latitude: number;
  longitude: number;
  cell: string;
  resolution: number;
  /** False when nothing was measured nearby, which is not the same as no coverage. */
  heard: boolean;
  grade: 'good' | 'fair' | 'weak' | null;
  best: CoverageSignal | null;
  gateways: CoverageSignal[];
}

export interface MapperFix {
  /** ISO-8601, or epoch milliseconds as `GeolocationPosition.timestamp` gives it. */
  time: string | number;
  latitude: number;
  longitude: number;
  accuracy?: number | null;
}

export interface MapperSession {
  id: string;
  devEui: string;
  startedBy: string | null;
  startedAt: string;
  endedAt: string | null;
  lastFixAt: string | null;
  fixes: number;
  samples: number;
  mine: boolean;
  recent?: Array<{ time: string; gatewayId: string; rssi: number; snr: number | null; latitude: number; longitude: number; grade: string }>;
}

type Bbox = readonly [west: number, south: number, east: number, north: number];

export class Airtime {
  constructor(private readonly core: Core) {}

  /** One device's time on air by UTC day, today live, against its plan's policy. */
  device(devEui: string, query: { days?: number } = {}, opts: Opts = {}): Promise<DeviceAirtime> {
    return this.core.request('GET', `/api/v1/devices/${seg(devEui)}/airtime`, { ...opts, query: { ...query } });
  }

  /** The org's devices on one day, heaviest share of their allowance first. */
  day(query: { day?: string; limit?: number } = {}, opts: Opts = {}): Promise<OrgAirtime> {
    return this.core.request('GET', '/api/v1/airtime', { ...opts, query: { ...query } });
  }
}

export class Coverage {
  constructor(private readonly core: Core) {}

  /** The org's cells: best gateway per cell, or one gateway's with `gatewayId`. */
  cells(query: { gatewayId?: string; resolution?: 6 | 7 | 8 | 9; bbox?: Bbox } = {}, opts: Opts = {}): Promise<CoverageCollection> {
    const { bbox, ...rest } = query;
    return this.core.request('GET', '/api/v1/coverage', {
      ...opts, query: { ...rest, bbox: bbox ? bbox.join(',') : undefined },
    });
  }

  at(latitude: number, longitude: number, opts: Opts = {}): Promise<CoverageAt> {
    return this.core.request('GET', '/api/v1/coverage/at', { ...opts, query: { latitude, longitude } });
  }

  /** The public layer: Pulzar-operated gateways only, from orgs that share. No key needed. */
  public(bbox: Bbox, query: { resolution?: 6 | 7 | 8 } = {}, opts: Opts = {}): Promise<CoverageCollection> {
    return this.core.request('GET', '/api/v1/public/coverage', {
      ...opts, query: { ...query, bbox: bbox.join(',') },
    });
  }

  settings(opts: Opts = {}): Promise<{ public: boolean; updatedAt: string | null }> {
    return this.core.request('GET', '/api/v1/coverage/settings', opts);
  }

  /** Org admin. */
  setPublic(value: boolean, opts: Opts = {}): Promise<{ public: boolean; updatedAt: string | null }> {
    return this.core.request('PUT', '/api/v1/coverage/settings', { ...opts, body: { public: value } });
  }

  startSession(devEui: string, opts: Opts = {}): Promise<MapperSession> {
    return this.core.request('POST', '/api/v1/coverage/sessions', { ...opts, body: { devEui } });
  }

  /** At most 120 per call; matched to uplinks heard within 15 seconds. */
  addFixes(sessionId: string, fixes: MapperFix[], opts: Opts = {}): Promise<MapperSession> {
    return this.core.request('POST', `/api/v1/coverage/sessions/${seg(sessionId)}/fixes`, { ...opts, body: { fixes } });
  }

  stopSession(sessionId: string, opts: Opts = {}): Promise<MapperSession> {
    return this.core.request('POST', `/api/v1/coverage/sessions/${seg(sessionId)}/stop`, opts);
  }
}
