/**
 * LoRa Basics Station gateways: registering one, and its CUPS and LNS
 * credentials -- net-api's routes/basic_station.py.
 *
 * `register` and `setup` return the credential files once; nothing can show
 * them again. Both, and `rotate` and `revoke`, need gateways:write and
 * org:admin; `status` needs gateways:read.
 */
import type { Core } from '../core.js';
import { seg } from '../util.js';

type Opts = { signal?: AbortSignal };
export type BasicStationAuth = 'token' | 'certificate';

export interface BasicStationBundle {
  gatewayId: string;
  auth: BasicStationAuth;
  cupsUri: string;
  lnsUri: string;
  /** File name to contents, as installed on the gateway. */
  files: Record<string, string>;
  signingKey: { crc: number; file: string } | null;
  versions: { cups: number; tc: number };
}

export interface BasicStationCredential {
  version: number;
  kind: BasicStationAuth;
  issuedAt: string;
  issuedVia: 'bundle' | 'cups';
  notAfter: string | null;
  id: string;
  pending: Omit<BasicStationCredential, 'pending'> | null;
}

export interface BasicStationStatus {
  gatewayId: string;
  operator: 'customer' | 'parkeze';
  auth: BasicStationAuth;
  state: 'active' | 'rotating' | 'revoked';
  cupsUri: string;
  lnsUri: string;
  connection: { state: 'connected' | 'disconnected' | 'never'; since: string | null; peer: string | null };
  lastCheckIn: string | null;
  station: { version: string | null; model: string | null; package: string | null } | null;
  credentials: { cups: BasicStationCredential | null; tc: BasicStationCredential | null };
  rotation: { requestedAt: string; requestedBy: string | null } | null;
  revokedAt: string | null;
}

export class BasicStation {
  constructor(private readonly core: Core) {}

  /** Add a Basics Station gateway to the org and issue its bundle. */
  register(gatewayId: string, name: string, options: Opts & { auth?: BasicStationAuth } = {}): Promise<BasicStationBundle & { name: string }> {
    const { auth = 'token', ...opts } = options;
    return this.core.request('POST', '/api/v1/gateways/basic-station', { ...opts, body: { gatewayId, name, auth } });
  }

  /** LNS connection, last CUPS check-in, and each credential's version. */
  status(gatewayId: string, opts: Opts = {}): Promise<BasicStationStatus> {
    return this.core.request('GET', `/api/v1/gateways/${seg(gatewayId)}/basic-station`, opts);
  }

  /** A new bundle for a gateway holding no working credentials. */
  setup(gatewayId: string, options: Opts & { auth?: BasicStationAuth } = {}): Promise<BasicStationBundle> {
    const { auth, ...opts } = options;
    return this.core.request('POST', `/api/v1/gateways/${seg(gatewayId)}/basic-station/setup`, {
      ...opts,
      body: auth ? { auth } : {},
    });
  }

  /** New credentials over CUPS at the next check-in; the old work until the gateway uses the new. */
  rotate(gatewayId: string, opts: Opts = {}): Promise<BasicStationStatus> {
    return this.core.request('POST', `/api/v1/gateways/${seg(gatewayId)}/basic-station/rotate`, opts);
  }

  /** Refuse every credential the gateway holds. `confirm` is its EUI. */
  revoke(gatewayId: string, confirm: string, opts: Opts = {}): Promise<BasicStationStatus> {
    return this.core.request('POST', `/api/v1/gateways/${seg(gatewayId)}/basic-station/revoke`, {
      ...opts,
      body: { confirm },
    });
  }
}
