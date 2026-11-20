/**
 * Gateways: the org's own, what they hear, and operating them -- net-api's
 * routes/gateways.py and plugins/gateway_ops.
 *
 * What a call may do is the caller's rights on that gateway: a gateways:read
 * key reads the org's gateways; restarting, updating, offering or removing one
 * needs gateways:write and org:admin. Shells and a gateway's web interface are
 * not in the API; a person opens them in the console.
 */
import type { Core } from '../core.js';
import { seg } from '../util.js';

type Opts = { signal?: AbortSignal };

/**
 * What the caller may do to one gateway. Empty for a gateway no org owns.
 * Network staff get `read`, and `transfer` (an offer) on an unowned one.
 */
export type GatewayAction = 'read' | 'manage' | 'console' | 'shell' | 'transfer' | 'release';

export interface Gateway {
  gatewayId: string;
  uuid: string | null;
  name: string;
  model: string | null;
  radios: Array<'lorawan' | 'ble'>;
  management: 'parkezeos' | 'package' | null;
  firmware: string | null;
  orgAlias: string | null;
  orgName: string | null;
  latitude: number | null;
  longitude: number | null;
  lastSeenAt: string | null;
  state: 'ONLINE' | 'OFFLINE' | 'NEVER_SEEN' | null;
  backhaul: 'cellular' | 'wifi' | 'ethernet' | 'mesh' | null;
  /** Only on the org's own gateways. */
  simIccid?: string | null;
  reachable?: boolean;
  can: GatewayAction[];
}

export interface GatewayDevices {
  result: Array<{ devEui: string; name: string | null; packets: number; lastHeard: string; bestRssi: number | null; bestSnr: number | null }>;
  silent: Array<{ devEui: string; name: string | null; application: string | null; profile: string | null; createdAt: string | null }>;
  days: number;
}

export interface GatewayNetworkPlane {
  kind: 'wireguard' | 'cellular';
  slug: string;
  name: string;
  owner: 'parkeze' | 'organization';
}

export interface GatewayNetwork {
  gatewayId: string;
  wireguard: GatewayNetworkPlane | null;
  cellular: GatewayNetworkPlane | null;
  sshCa: boolean;
}

export interface GatewayBackhaul {
  gatewayId: string;
  wireguard: Record<string, unknown>;
  cellular: Record<string, unknown>;
  override: string | null;
  path: 'override' | 'wireguard' | 'cellular' | null;
  /** True when a connection now would bill the SIM. */
  metered: boolean | null;
  reachable: boolean;
}

export interface GatewayTransfer {
  id: string;
  gatewayId: string;
  gatewayName: string | null;
  from: { alias: string; displayName: string } | null;
  to: { alias: string; displayName: string };
  direction?: 'incoming' | 'outgoing';
  status: 'offered' | 'accepting' | 'accepted' | 'declined' | 'cancelled' | 'expired' | 'failed';
  note: string | null;
  offeredBy: string | null;
  offeredAt: string;
  expiresAt: string;
  decidedBy: string | null;
  decidedAt: string | null;
  failure: string | null;
  warnings: string[];
  /** Network staff offered a gateway no organization owned. */
  byStaff?: boolean;
}

export class Gateways {
  constructor(private readonly core: Core) {}

  /** The org's gateways, and community ones on its map. */
  async list(opts: Opts = {}): Promise<Gateway[]> {
    const page = await this.core.request<{ result: Gateway[] }>('GET', '/api/v1/gateways', opts);
    return page.result;
  }

  metrics(gatewayId: string, query: { hours?: number; aggregation?: 'HOUR' | 'DAY' | 'MONTH' } = {}, opts: Opts = {}): Promise<Record<string, unknown>> {
    return this.core.request('GET', `/api/v1/gateways/${seg(gatewayId)}/metrics`, { ...opts, query: { ...query } });
  }

  /** Devices it heard, and devices in its tenant never heard by anything. */
  devices(gatewayId: string, query: { days?: number } = {}, opts: Opts = {}): Promise<GatewayDevices> {
    return this.core.request('GET', `/api/v1/gateways/${seg(gatewayId)}/devices`, { ...opts, query: { ...query } });
  }

  /** Asks the gateway itself, over its management link. */
  status(gatewayId: string, opts: Opts = {}): Promise<Record<string, unknown>> {
    return this.core.request('GET', `/api/v1/gateway-ops/${seg(gatewayId)}/status`, opts);
  }

  /** Which network its tunnel and SIM are on: the org's own or Pulzar's. Never touches the gateway. */
  network(gatewayId: string, opts: Opts = {}): Promise<GatewayNetwork> {
    return this.core.request('GET', `/api/v1/gateways/${seg(gatewayId)}/network`, opts);
  }

  /** Never touches the gateway. */
  backhaul(gatewayId: string, opts: Opts = {}): Promise<GatewayBackhaul> {
    return this.core.request('GET', `/api/v1/gateway-ops/${seg(gatewayId)}/backhaul`, opts);
  }

  restart(gatewayId: string, opts: Opts = {}): Promise<{ exitStatus: number; output: string }> {
    return this.core.request('POST', `/api/v1/gateway-ops/${seg(gatewayId)}/restart`, opts);
  }

  /** Offer it to another org by alias; `confirm` repeats the EUI. */
  offer(gatewayId: string, body: { toOrg: string; confirm: string; note?: string }, opts: Opts = {}): Promise<GatewayTransfer> {
    return this.core.request('POST', `/api/v1/gateway-ops/gateways/${seg(gatewayId)}/transfer`, { ...opts, body });
  }

  async transfers(opts: Opts = {}): Promise<GatewayTransfer[]> {
    const page = await this.core.request<{ result: GatewayTransfer[] }>('GET', '/api/v1/gateway-ops/transfers', opts);
    return page.result;
  }

  accept(transferId: string, confirm: string, opts: Opts = {}): Promise<Record<string, unknown>> {
    return this.core.request('POST', `/api/v1/gateway-ops/transfers/${seg(transferId)}/accept`, { ...opts, body: { confirm } });
  }

  decline(transferId: string, opts: Opts = {}): Promise<GatewayTransfer> {
    return this.core.request('POST', `/api/v1/gateway-ops/transfers/${seg(transferId)}/decline`, opts);
  }

  cancel(transferId: string, opts: Opts = {}): Promise<GatewayTransfer> {
    return this.core.request('POST', `/api/v1/gateway-ops/transfers/${seg(transferId)}/cancel`, opts);
  }
}
