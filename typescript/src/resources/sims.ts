/**
 * SIMs: the ones in the org's gateways, and on its own cellular network --
 * net-api's routes/sims.py.
 *
 * What a call may do is the caller's rights on that SIM, which each entry
 * carries as `can`: a gateways:read key reads the org's SIMs; changing or
 * resetting one needs gateways:write and org:admin. Other orgs' SIMs answer
 * 404. A SIM's device web UI is not in the API; a person opens it in the
 * console.
 */
import type { Core } from '../core.js';
import { seg } from '../util.js';

type Opts = { signal?: AbortSignal };
type OnNetwork = { network?: string };

export type SimAction = 'read' | 'manage' | 'console';

export interface Sim {
  iccid: string;
  status?: string;
  label?: string | null;
  currentQuotaMb?: number | null;
  ipAddress?: string | null;
  networkId: string | null;
  gateway: { gatewayId: string; name: string | null; model: string | null } | null;
  claim: Record<string, unknown> | null;
  can: SimAction[];
  [key: string]: unknown;
}

export interface SimList {
  result: Sim[];
  /** The org's gateways bound to an ICCID the account no longer returns. */
  orphaned: Array<{ gatewayId: string; name: string | null; iccid: string }>;
}

export interface SimUsageDay {
  day: string;
  remainingMb: number;
  usedMb: number | null;
  toppedUpMb: number | null;
  sims: number;
  notEnabled: number;
}

export class Sims {
  constructor(private readonly core: Core) {}

  list(query: OnNetwork = {}, opts: Opts = {}): Promise<SimList> {
    return this.core.request('GET', '/api/v1/sims', { ...opts, query: { ...query } });
  }

  /** Whether each SIM is attached right now, by ICCID. Null is unknown, not off. */
  status(query: OnNetwork = {}, opts: Opts = {}): Promise<{ result: Record<string, string | null>; cached: boolean }> {
    return this.core.request('GET', '/api/v1/sims/status', { ...opts, query: { ...query } });
  }

  usage(query: { days?: number } = {}, opts: Opts = {}): Promise<{ result: SimUsageDay[]; recordingSince: string | null }> {
    return this.core.request('GET', '/api/v1/sims/usage', { ...opts, query: { ...query } });
  }

  get(iccid: string, query: OnNetwork = {}, opts: Opts = {}): Promise<Record<string, unknown> & { can: SimAction[] }> {
    return this.core.request('GET', `/api/v1/sims/${seg(iccid)}/detail`, { ...opts, query: { ...query } });
  }

  billing(iccid: string, query: OnNetwork = {}, opts: Opts = {}): Promise<Record<string, unknown>> {
    return this.core.request('GET', `/api/v1/sims/${seg(iccid)}/billing`, { ...opts, query: { ...query } });
  }

  /** Enable or disable it (disabling takes its gateway off cellular), lock it to its modem, or rename it. */
  update(iccid: string, body: { enabled?: boolean; imeiLock?: boolean; label?: string }, query: OnNetwork = {}, opts: Opts = {}): Promise<Record<string, unknown>> {
    return this.core.request('PATCH', `/api/v1/sims/${seg(iccid)}`, { ...opts, query: { ...query }, body });
  }

  /** Force a re-attach. Its gateway is off cellular for up to a minute. */
  reset(iccid: string, query: OnNetwork = {}, opts: Opts = {}): Promise<Record<string, unknown>> {
    return this.core.request('POST', `/api/v1/sims/${seg(iccid)}/reset`, { ...opts, query: { ...query } });
  }
}
