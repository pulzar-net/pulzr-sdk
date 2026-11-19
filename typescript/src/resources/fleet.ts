import type { Core } from '../core.js';
import type { FirmwareDeviceStage } from '../events.js';
import { seg } from '../util.js';

type Opts = { signal?: AbortSignal };

export interface MulticastGroup {
  id: string;
  name: string;
  applicationId: string;
  region: string;
  groupType: 'B' | 'C';
  dr: number;
  frequency: number;
  mcAddr: string;
  fCnt: number | null;
  pingSlotPeriodicity?: number;
  schedulingType?: 'delay' | 'gps_time';
  devices?: Array<{ devEui: string; name: string | null; lastSeenAt: string | null }>;
  gateways?: Array<{ gatewayId: string; name: string | null; state: string | null }>;
}

export interface MulticastGroupInput {
  name: string;
  applicationId: string;
  region: string;
  groupType?: 'B' | 'C';
  /** Defaults to the region's RX2 data rate. */
  dr?: number;
  /** Hz. Defaults to the region's RX2 frequency. */
  frequency?: number;
  pingSlotPeriodicity?: number;
  schedulingType?: 'delay' | 'gps_time';
}

export interface Relay {
  devEui: string;
  name: string | null;
  applicationId: string;
  applicationName: string | null;
  deviceCount: number;
}

export interface FirmwareImage {
  id: string;
  name: string;
  version: string;
  filename: string;
  sizeBytes: number;
  sha256: string;
  /** Null only on an image uploaded before a type was required; it is not deployed until set. */
  deviceTypeId: string | null;
  deviceType: { id: string; vendor: string; model: string } | null;
  uploadedBy: string;
  uploadedAt: string;
}

export type FirmwareDeploymentStatus = 'draft' | 'running' | 'finished' | 'failed' | 'canceled';

export interface FirmwareEstimate {
  fragmentSize: number;
  fragments: number;
  redundantFragments: number;
  frames: number;
  airtimePerFrameMs: number;
  airtimeSeconds: number;
  spacingSeconds: number;
  dutyCycle: number | null;
  sessionSeconds: number;
  setupSeconds: { min: number; max: number };
  totalSeconds: { min: number; max: number };
}

/** Which devices, and how the session runs. Every selector given must hold. */
export interface FirmwareDeploymentInput {
  imageId: string;
  devEuis?: string[];
  deviceTypeId?: string;
  applicationId?: string;
  tags?: Record<string, string>;
  groupType?: 'B' | 'C';
  dr?: number;
  frequency?: number;
  pingSlotPeriodicity?: number;
  schedulingType?: 'delay' | 'gps_time';
  redundancyPercent?: number;
  fragmentSize?: number;
  unicastMaxRetries?: number;
  requestStatus?: 'none' | 'after_enqueue' | 'after_session_timeout';
  descriptor?: string;
  completeTags?: Record<string, string>;
  gatewayIds?: string[];
}

export interface FirmwarePlan {
  image: FirmwareImage;
  applicationId: string;
  deviceProfile: { id: string; name: string; region: string };
  devices: Array<{ devEui: string; name: string | null }>;
  params: Record<string, unknown>;
  /** Null for a region without a payload table (AS923, AU915). */
  estimate: FirmwareEstimate | null;
}

export interface FirmwareDeployment {
  id: string;
  name: string;
  status: FirmwareDeploymentStatus;
  imageId: string;
  /** The image's. */
  deviceTypeId: string | null;
  applicationId: string;
  deviceProfileId: string;
  region: string | null;
  params: Record<string, unknown>;
  estimate: FirmwareEstimate | null;
  lnsJob: string | null;
  error: string | null;
  createdBy: string;
  createdAt: string;
  startedBy: string | null;
  startedAt: string | null;
  finishedAt: string | null;
  canceledAt: string | null;
  progress?: Record<FirmwareDeviceStage | 'total', number>;
  devices?: Array<{ devEui: string; stage: FirmwareDeviceStage; error: string | null; completedAt: string | null }>;
}

export class MulticastGroups {
  constructor(private readonly core: Core) {}

  async list(opts: Opts = {}): Promise<MulticastGroup[]> {
    return (await this.core.request<{ result: MulticastGroup[] }>('GET', '/api/v1/multicast-groups', opts)).result;
  }

  /** The only answer that carries the session keys; they go on the devices out of band. */
  create(input: MulticastGroupInput, opts: Opts = {}): Promise<MulticastGroup & { keys: { mcNwkSKey: string; mcAppSKey: string } }> {
    return this.core.request('POST', '/api/v1/multicast-groups', { ...opts, body: input });
  }

  get(id: string, opts: Opts = {}): Promise<MulticastGroup> {
    return this.core.request('GET', `/api/v1/multicast-groups/${seg(id)}`, opts);
  }

  async delete(id: string, opts: Opts = {}): Promise<void> {
    await this.core.request('DELETE', `/api/v1/multicast-groups/${seg(id)}`, opts);
  }

  addDevice(id: string, devEui: string, opts: Opts = {}): Promise<{ added: string }> {
    return this.core.request('POST', `/api/v1/multicast-groups/${seg(id)}/devices`, { ...opts, body: { devEui } });
  }

  removeDevice(id: string, devEui: string, opts: Opts = {}): Promise<{ removed: string }> {
    return this.core.request('DELETE', `/api/v1/multicast-groups/${seg(id)}/devices/${seg(devEui)}`, opts);
  }

  addGateway(id: string, gatewayId: string, opts: Opts = {}): Promise<{ added: string }> {
    return this.core.request('POST', `/api/v1/multicast-groups/${seg(id)}/gateways`, { ...opts, body: { gatewayId } });
  }

  removeGateway(id: string, gatewayId: string, opts: Opts = {}): Promise<{ removed: string }> {
    return this.core.request('DELETE', `/api/v1/multicast-groups/${seg(id)}/gateways/${seg(gatewayId)}`, opts);
  }

  /** One downlink for every member; `data` is base64. */
  send(id: string, fPort: number, data: string, opts: Opts = {}): Promise<{ fCnt: number }> {
    return this.core.request('POST', `/api/v1/multicast-groups/${seg(id)}/queue`, { ...opts, body: { fPort, data } });
  }

  async flush(id: string, opts: Opts = {}): Promise<void> {
    await this.core.request('DELETE', `/api/v1/multicast-groups/${seg(id)}/queue`, opts);
  }
}

export class Relays {
  constructor(private readonly core: Core) {}

  async list(opts: Opts = {}): Promise<Relay[]> {
    return (await this.core.request<{ result: Relay[] }>('GET', '/api/v1/relays', opts)).result;
  }

  async devices(relayDevEui: string, opts: Opts = {}): Promise<Array<{ devEui: string; name: string | null; createdAt: string | null }>> {
    return (await this.core.request<{ result: Array<{ devEui: string; name: string | null; createdAt: string | null }> }>(
      'GET', `/api/v1/relays/${seg(relayDevEui)}/devices`, opts)).result;
  }

  addDevice(relayDevEui: string, devEui: string, opts: Opts = {}): Promise<{ added: string }> {
    return this.core.request('POST', `/api/v1/relays/${seg(relayDevEui)}/devices`, { ...opts, body: { devEui } });
  }

  removeDevice(relayDevEui: string, devEui: string, opts: Opts = {}): Promise<{ removed: string }> {
    return this.core.request('DELETE', `/api/v1/relays/${seg(relayDevEui)}/devices/${seg(devEui)}`, opts);
  }
}

/** Images are uploaded as multipart from the console or the Python SDK. */
export class Firmware {
  constructor(private readonly core: Core) {}

  async images(opts: Opts = {}): Promise<FirmwareImage[]> {
    return (await this.core.request<{ result: FirmwareImage[] }>('GET', '/api/v1/firmware/images', opts)).result;
  }

  /** Org admin. On an image with no type, or one no deployment used. */
  setImageType(id: string, deviceTypeId: string, opts: Opts = {}): Promise<FirmwareImage> {
    return this.core.request('PATCH', `/api/v1/firmware/images/${seg(id)}`, { ...opts, body: { deviceTypeId } });
  }

  /** What a deployment would do and how long it would take; changes nothing. */
  plan(input: FirmwareDeploymentInput, opts: Opts = {}): Promise<FirmwarePlan> {
    return this.core.request('POST', '/api/v1/firmware/plan', { ...opts, body: input });
  }

  /** Org admin. A draft: nothing reaches the LNS until `start`. */
  create(name: string, input: FirmwareDeploymentInput, opts: Opts = {}): Promise<FirmwareDeployment> {
    return this.core.request('POST', '/api/v1/firmware/deployments', { ...opts, body: { name, ...input } });
  }

  async list(opts: Opts = {}): Promise<FirmwareDeployment[]> {
    return (await this.core.request<{ result: FirmwareDeployment[] }>('GET', '/api/v1/firmware/deployments', opts)).result;
  }

  get(id: string, opts: Opts = {}): Promise<FirmwareDeployment> {
    return this.core.request('GET', `/api/v1/firmware/deployments/${seg(id)}`, opts);
  }

  /** Org admin. Reflashes devices: `confirm` is the deployment's name, exactly. */
  start(id: string, confirm: string, opts: Opts = {}): Promise<FirmwareDeployment> {
    return this.core.request('POST', `/api/v1/firmware/deployments/${seg(id)}/start`, { ...opts, body: { confirm } });
  }

  cancel(id: string, opts: Opts = {}): Promise<FirmwareDeployment> {
    return this.core.request('POST', `/api/v1/firmware/deployments/${seg(id)}/cancel`, opts);
  }
}
